from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
import json
import os
import uuid
from datetime import datetime, date, timedelta
from functools import wraps
import hashlib
import requests as http_requests
import calendar

app = Flask(__name__)
app.secret_key = 'kindergarten_secret_key_2024_xK9#mP2'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

DATA_DIR = 'data'

# ─── Data helpers ─────────────────────────────────────────────────────────────

def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return []

def save_json(filename, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_settings():
    path = os.path.join(DATA_DIR, 'settings.json')
    default = {
        "name": "Smart Kindergarten",
        "currency": "UZS",
        "bot_token": "",
        "required_channels": [],
        "logo": ""
    }
    if not os.path.exists(path):
        save_json('settings.json', default)
        return default
    with open(path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            for k, v in default.items():
                if k not in data:
                    data[k] = v
            return data
        except:
            return default

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs('static/uploads', exist_ok=True)

    # Init admins
    admins_path = os.path.join(DATA_DIR, 'admins.json')
    if not os.path.exists(admins_path):
        save_json('admins.json', [{
            "id": "admin-1",
            "login": "993190712",
            "password": hash_password("12345678"),
            "name": "Administrator"
        }])

    for f in ['students.json', 'attendance.json', 'payments.json', 'notifications.json']:
        path = os.path.join(DATA_DIR, f)
        if not os.path.exists(path):
            save_json(f, [])

    load_settings()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def get_admin():
    admins = load_json('admins.json')
    for a in admins:
        if a['id'] == session.get('admin_id'):
            return a
    return None

# ─── Attendance helpers ────────────────────────────────────────────────────────

def get_working_days(year, month):
    """Return count of working (Mon–Fri) days in a month."""
    cal = calendar.monthcalendar(year, month)
    days = 0
    for week in cal:
        for i, d in enumerate(week):
            if d != 0 and i < 5:  # Mon=0 … Fri=4
                days += 1
    return days

def get_attended_days(student_id, year, month):
    attendance = load_json('attendance.json')
    count = 0
    for rec in attendance:
        if rec['student_id'] != student_id:
            continue
        try:
            d = datetime.strptime(rec['date'], '%Y-%m-%d')
            if d.year == year and d.month == month and rec['status'] == 'present':
                count += 1
        except:
            pass
    return count

def get_absent_days(student_id, year, month):
    attendance = load_json('attendance.json')
    count = 0
    for rec in attendance:
        if rec['student_id'] != student_id:
            continue
        try:
            d = datetime.strptime(rec['date'], '%Y-%m-%d')
            if d.year == year and d.month == month and rec['status'] == 'absent':
                count += 1
        except:
            pass
    return count

def calc_payable_amount(student, year, month):
    working = get_working_days(year, month)
    absent = get_absent_days(student['id'], year, month)
    payable_days = max(working - absent, 0)
    daily = student['monthly_fee'] / working if working else 0
    return round(daily * payable_days)

def get_paid_amount(student_id, year, month):
    payments = load_json('payments.json')
    total = 0
    for p in payments:
        if p['student_id'] != student_id:
            continue
        try:
            d = datetime.strptime(p['date'], '%Y-%m-%d')
            if d.year == year and d.month == month:
                total += p['amount']
        except:
            pass
    return total

# ─── Auth routes ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'admin_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        login_val = data.get('login', '').strip()
        password = data.get('password', '')
        remember = data.get('remember', False)

        admins = load_json('admins.json')
        for admin in admins:
            if admin['login'] == login_val and admin['password'] == hash_password(password):
                session['admin_id'] = admin['id']
                session['admin_name'] = admin['name']
                if remember:
                    session.permanent = True
                    app.permanent_session_lifetime = timedelta(days=30)
                return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Нотўғри логин ёки парол'})
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    settings = load_settings()
    return render_template('dashboard.html', settings=settings, admin_name=session.get('admin_name'))

@app.route('/api/dashboard-stats')
@login_required
def dashboard_stats():
    students = load_json('students.json')
    payments = load_json('payments.json')
    attendance = load_json('attendance.json')

    now = datetime.now()
    y, m = now.year, now.month
    today_str = now.strftime('%Y-%m-%d')

    total_students = len(students)
    active_students = sum(1 for s in students if s.get('status') == 'active')

    # Monthly income
    monthly_income = sum(p['amount'] for p in payments
                         if p['date'].startswith(f'{y}-{m:02d}'))

    # Debtors + unpaid this month
    debtors = 0
    unpaid = 0
    for s in students:
        if s.get('status') != 'active':
            continue
        payable = calc_payable_amount(s, y, m)
        paid = get_paid_amount(s['id'], y, m)
        if paid < payable:
            debtors += 1
            unpaid += payable - paid

    # Today attendance
    today_att = sum(1 for a in attendance
                    if a['date'] == today_str and a['status'] == 'present')

    # Recent payments (last 5)
    sorted_payments = sorted(payments, key=lambda x: x.get('date',''), reverse=True)[:5]
    recent_payments = []
    for p in sorted_payments:
        s = next((st for st in students if st['id'] == p['student_id']), None)
        recent_payments.append({
            **p,
            'student_name': f"{s['first_name']} {s['last_name']}" if s else 'Unknown'
        })

    # Recent students
    sorted_students = sorted(students, key=lambda x: x.get('join_date',''), reverse=True)[:5]

    # Recent attendance
    sorted_att = sorted(attendance, key=lambda x: x.get('date',''), reverse=True)[:5]
    recent_att = []
    for a in sorted_att:
        s = next((st for st in students if st['id'] == a['student_id']), None)
        recent_att.append({
            **a,
            'student_name': f"{s['first_name']} {s['last_name']}" if s else 'Unknown'
        })

    return jsonify({
        'total_students': total_students,
        'active_students': active_students,
        'debtors': debtors,
        'monthly_income': monthly_income,
        'unpaid': unpaid,
        'today_attendance': today_att,
        'recent_payments': recent_payments,
        'recent_students': sorted_students[:5],
        'recent_attendance': recent_att
    })

# ─── Students ─────────────────────────────────────────────────────────────────

@app.route('/students')
@login_required
def students_page():
    settings = load_settings()
    return render_template('students.html', settings=settings, admin_name=session.get('admin_name'))

@app.route('/api/students', methods=['GET'])
@login_required
def get_students():
    students = load_json('students.json')
    group = request.args.get('group', '')
    search = request.args.get('search', '').lower()
    status = request.args.get('status', '')

    result = students
    if group:
        result = [s for s in result if s.get('group', '') == group]
    if status:
        result = [s for s in result if s.get('status', '') == status]
    if search:
        result = [s for s in result if
                  search in s.get('first_name', '').lower() or
                  search in s.get('last_name', '').lower() or
                  search in s.get('parent_name', '').lower() or
                  search in s.get('parent_phone', '').lower() or
                  search in s.get('id', '').lower()]

    return jsonify(result)

@app.route('/api/students', methods=['POST'])
@login_required
def add_student():
    data = request.get_json()
    students = load_json('students.json')

    # Check duplicate
    phone = data.get('parent_phone', '').strip()
    fname = data.get('first_name', '').strip()
    lname = data.get('last_name', '').strip()
    for s in students:
        if s['first_name'].lower() == fname.lower() and s['last_name'].lower() == lname.lower():
            return jsonify({'success': False, 'message': 'Бу исмли ўқувчи аллақачон мавжуд'})

    student = {
        'id': 'STU-' + str(uuid.uuid4())[:8].upper(),
        'first_name': fname,
        'last_name': lname,
        'birth_date': data.get('birth_date', ''),
        'parent_name': data.get('parent_name', '').strip(),
        'parent_phone': phone,
        'group': data.get('group', '').strip(),
        'monthly_fee': int(data.get('monthly_fee', 0)),
        'payment_due_day': int(data.get('payment_due_day', 1)),
        'join_date': data.get('join_date', date.today().isoformat()),
        'status': data.get('status', 'active'),
        'image': data.get('image', ''),
        'telegram_chat_id': data.get('telegram_chat_id', ''),
        'notes': data.get('notes', '')
    }
    students.append(student)
    save_json('students.json', students)

    # Add notification
    add_notification(f"Yangi o'quvchi qo'shildi: {fname} {lname}", 'info')

    return jsonify({'success': True, 'student': student})

@app.route('/api/students/<student_id>', methods=['GET'])
@login_required
def get_student(student_id):
    students = load_json('students.json')
    s = next((s for s in students if s['id'] == student_id), None)
    if not s:
        return jsonify({'success': False, 'message': 'Ўқувчи топилмади'}), 404
    return jsonify(s)

@app.route('/api/students/<student_id>', methods=['PUT'])
@login_required
def update_student(student_id):
    data = request.get_json()
    students = load_json('students.json')
    for i, s in enumerate(students):
        if s['id'] == student_id:
            students[i].update({
                'first_name': data.get('first_name', s['first_name']).strip(),
                'last_name': data.get('last_name', s['last_name']).strip(),
                'birth_date': data.get('birth_date', s['birth_date']),
                'parent_name': data.get('parent_name', s['parent_name']).strip(),
                'parent_phone': data.get('parent_phone', s['parent_phone']).strip(),
                'group': data.get('group', s['group']).strip(),
                'monthly_fee': int(data.get('monthly_fee', s['monthly_fee'])),
                'payment_due_day': int(data.get('payment_due_day', s['payment_due_day'])),
                'status': data.get('status', s['status']),
                'image': data.get('image', s.get('image', '')),
                'telegram_chat_id': data.get('telegram_chat_id', s.get('telegram_chat_id', '')),
                'notes': data.get('notes', s.get('notes', ''))
            })
            save_json('students.json', students)
            return jsonify({'success': True, 'student': students[i]})
    return jsonify({'success': False, 'message': 'Ўқувчи топилмади'}), 404

@app.route('/api/students/<student_id>', methods=['DELETE'])
@login_required
def delete_student(student_id):
    students = load_json('students.json')
    students = [s for s in students if s['id'] != student_id]
    save_json('students.json', students)
    return jsonify({'success': True})

@app.route('/api/groups')
@login_required
def get_groups():
    students = load_json('students.json')
    groups = list(set(s.get('group', '') for s in students if s.get('group')))
    return jsonify(sorted(groups))

# ─── Attendance ───────────────────────────────────────────────────────────────

@app.route('/attendance')
@login_required
def attendance_page():
    settings = load_settings()
    return render_template('attendance.html', settings=settings, admin_name=session.get('admin_name'))

@app.route('/api/attendance', methods=['GET'])
@login_required
def get_attendance():
    att = load_json('attendance.json')
    date_filter = request.args.get('date', '')
    student_id = request.args.get('student_id', '')
    month = request.args.get('month', '')

    result = att
    if date_filter:
        result = [a for a in result if a['date'] == date_filter]
    if student_id:
        result = [a for a in result if a['student_id'] == student_id]
    if month:
        result = [a for a in result if a['date'].startswith(month)]

    return jsonify(result)

@app.route('/api/attendance', methods=['POST'])
@login_required
def mark_attendance():
    data = request.get_json()
    att = load_json('attendance.json')
    student_id = data['student_id']
    att_date = data['date']
    status = data['status']  # present / absent / excused

    # Update or insert
    found = False
    for i, a in enumerate(att):
        if a['student_id'] == student_id and a['date'] == att_date:
            att[i]['status'] = status
            att[i]['note'] = data.get('note', '')
            found = True
            break
    if not found:
        att.append({
            'id': str(uuid.uuid4())[:8],
            'student_id': student_id,
            'date': att_date,
            'status': status,
            'note': data.get('note', ''),
            'marked_by': session.get('admin_name', 'Admin'),
            'created_at': datetime.now().isoformat()
        })
    save_json('attendance.json', att)
    return jsonify({'success': True})

@app.route('/api/attendance/bulk', methods=['POST'])
@login_required
def bulk_attendance():
    data = request.get_json()
    att_date = data['date']
    records = data['records']  # [{student_id, status, note}]

    att = load_json('attendance.json')
    for rec in records:
        found = False
        for i, a in enumerate(att):
            if a['student_id'] == rec['student_id'] and a['date'] == att_date:
                att[i]['status'] = rec['status']
                att[i]['note'] = rec.get('note', '')
                found = True
                break
        if not found:
            att.append({
                'id': str(uuid.uuid4())[:8],
                'student_id': rec['student_id'],
                'date': att_date,
                'status': rec['status'],
                'note': rec.get('note', ''),
                'marked_by': session.get('admin_name', 'Admin'),
                'created_at': datetime.now().isoformat()
            })
    save_json('attendance.json', att)
    return jsonify({'success': True})

@app.route('/api/attendance/month-summary')
@login_required
def month_summary():
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    students = load_json('students.json')

    result = []
    working_days = get_working_days(year, month)
    for s in students:
        if s.get('status') != 'active':
            continue
        attended = get_attended_days(s['id'], year, month)
        absent = get_absent_days(s['id'], year, month)
        payable = calc_payable_amount(s, year, month)
        paid = get_paid_amount(s['id'], year, month)
        result.append({
            'student': s,
            'working_days': working_days,
            'attended': attended,
            'absent': absent,
            'payable_amount': payable,
            'paid_amount': paid,
            'debt': max(payable - paid, 0)
        })
    return jsonify(result)

# ─── Payments ─────────────────────────────────────────────────────────────────

@app.route('/payments')
@login_required
def payments_page():
    settings = load_settings()
    return render_template('payments.html', settings=settings, admin_name=session.get('admin_name'))

@app.route('/api/payments', methods=['GET'])
@login_required
def get_payments():
    payments = load_json('payments.json')
    student_id = request.args.get('student_id', '')
    month = request.args.get('month', '')

    result = payments
    if student_id:
        result = [p for p in result if p['student_id'] == student_id]
    if month:
        result = [p for p in result if p['date'].startswith(month)]

    result = sorted(result, key=lambda x: x.get('date', ''), reverse=True)
    return jsonify(result)

@app.route('/api/payments', methods=['POST'])
@login_required
def add_payment():
    data = request.get_json()
    payments = load_json('payments.json')
    students = load_json('students.json')

    student_id = data['student_id']
    student = next((s for s in students if s['id'] == student_id), None)
    if not student:
        return jsonify({'success': False, 'message': 'Ўқувчи топилмади'})

    receipt_id = 'RCP-' + str(uuid.uuid4())[:8].upper()
    payment = {
        'id': receipt_id,
        'student_id': student_id,
        'student_name': f"{student['first_name']} {student['last_name']}",
        'amount': int(data['amount']),
        'date': data.get('date', date.today().isoformat()),
        'month': data.get('month', datetime.now().strftime('%Y-%m')),
        'type': data.get('type', 'full'),  # full / partial
        'note': data.get('note', ''),
        'admin_name': session.get('admin_name', 'Admin'),
        'created_at': datetime.now().isoformat()
    }
    payments.append(payment)
    save_json('payments.json', payments)

    add_notification(f"To'lov qabul qilindi: {student['first_name']} {student['last_name']} - {payment['amount']:,} UZS", 'payment')

    return jsonify({'success': True, 'payment': payment, 'receipt_id': receipt_id})

@app.route('/api/payments/<payment_id>', methods=['DELETE'])
@login_required
def delete_payment(payment_id):
    payments = load_json('payments.json')
    payments = [p for p in payments if p['id'] != payment_id]
    save_json('payments.json', payments)
    return jsonify({'success': True})

@app.route('/api/student-balance/<student_id>')
@login_required
def student_balance(student_id):
    students = load_json('students.json')
    student = next((s for s in students if s['id'] == student_id), None)
    if not student:
        return jsonify({'success': False}), 404

    now = datetime.now()
    y, m = now.year, now.month

    payable = calc_payable_amount(student, y, m)
    paid = get_paid_amount(student_id, y, m)
    working = get_working_days(y, m)
    absent = get_absent_days(student_id, y, m)
    attended = get_attended_days(student_id, y, m)

    return jsonify({
        'student': student,
        'payable_amount': payable,
        'paid_amount': paid,
        'debt': max(payable - paid, 0),
        'working_days': working,
        'absent_days': absent,
        'attended_days': attended
    })

# ─── Receipt ──────────────────────────────────────────────────────────────────

@app.route('/receipt/<payment_id>')
@login_required
def receipt_page(payment_id):
    payments = load_json('payments.json')
    payment = next((p for p in payments if p['id'] == payment_id), None)
    settings = load_settings()
    return render_template('receipt.html', payment=payment, settings=settings)

# ─── Parents portal ───────────────────────────────────────────────────────────

@app.route('/parent')
def parent_portal():
    settings = load_settings()
    return render_template('parent.html', settings=settings)

@app.route('/api/parent/lookup')
def parent_lookup():
    phone = request.args.get('phone', '').strip()
    student_id = request.args.get('student_id', '').strip()
    students = load_json('students.json')

    student = None
    if student_id:
        student = next((s for s in students if s['id'] == student_id), None)
    elif phone:
        student = next((s for s in students if s.get('parent_phone', '') == phone), None)

    if not student:
        return jsonify({'success': False, 'message': 'Ўқувчи топилмади'})

    now = datetime.now()
    y, m = now.year, now.month

    payments = load_json('payments.json')
    student_payments = [p for p in payments if p['student_id'] == student['id']]
    student_payments = sorted(student_payments, key=lambda x: x.get('date',''), reverse=True)

    att = load_json('attendance.json')
    student_att = [a for a in att if a['student_id'] == student['id']]

    payable = calc_payable_amount(student, y, m)
    paid = get_paid_amount(student['id'], y, m)

    notifications = load_json('notifications.json')
    student_notifs = [n for n in notifications if n.get('target') in ['all', student['id']]][-10:]

    return jsonify({
        'success': True,
        'student': {k: v for k, v in student.items() if k != 'telegram_chat_id'},
        'payments': student_payments[:20],
        'attendance': student_att[-30:],
        'current_month': {
            'payable': payable,
            'paid': paid,
            'debt': max(payable - paid, 0)
        },
        'notifications': student_notifs
    })

# ─── Notifications ────────────────────────────────────────────────────────────

def add_notification(message, notif_type='info', target='all'):
    notifications = load_json('notifications.json')
    notifications.append({
        'id': str(uuid.uuid4())[:8],
        'message': message,
        'type': notif_type,
        'target': target,
        'read': False,
        'created_at': datetime.now().isoformat()
    })
    # Keep last 200
    if len(notifications) > 200:
        notifications = notifications[-200:]
    save_json('notifications.json', notifications)

@app.route('/notifications')
@login_required
def notifications_page():
    settings = load_settings()
    return render_template('notifications.html', settings=settings, admin_name=session.get('admin_name'))

@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    notifications = load_json('notifications.json')
    return jsonify(sorted(notifications, key=lambda x: x.get('created_at',''), reverse=True))

@app.route('/api/notifications/unread-count')
@login_required
def unread_count():
    notifications = load_json('notifications.json')
    count = sum(1 for n in notifications if not n.get('read', False))
    return jsonify({'count': count})

@app.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    notifications = load_json('notifications.json')
    for n in notifications:
        n['read'] = True
    save_json('notifications.json', notifications)
    return jsonify({'success': True})

@app.route('/api/notifications/dismiss/<notif_id>', methods=['DELETE'])
@login_required
def dismiss_notification(notif_id):
    notifications = load_json('notifications.json')
    notifications = [n for n in notifications if n['id'] != notif_id]
    save_json('notifications.json', notifications)
    return jsonify({'success': True})

@app.route('/api/notifications/smart-check')
@login_required
def smart_check():
    students = load_json('students.json')
    today = date.today()
    now = datetime.now()
    y, m = now.year, now.month
    alerts = []

    for s in students:
        if s.get('status') != 'active':
            continue

        # Birthday check
        try:
            bd = datetime.strptime(s['birth_date'], '%Y-%m-%d')
            if bd.month == today.month and bd.day == today.day:
                alerts.append({'type': 'birthday', 'message': f"🎂 Bugun {s['first_name']} {s['last_name']} ning tug'ilgan kuni!", 'student': s})
        except:
            pass

        # Debt check
        payable = calc_payable_amount(s, y, m)
        paid = get_paid_amount(s['id'], y, m)
        if paid < payable:
            debt = payable - paid
            alerts.append({'type': 'debt', 'message': f"💳 {s['first_name']} {s['last_name']}: qarzdorlik {debt:,} UZS", 'student': s})

        # Today absence
        att = load_json('attendance.json')
        today_str = today.isoformat()
        today_att = next((a for a in att if a['student_id'] == s['id'] and a['date'] == today_str), None)
        if today_att and today_att['status'] == 'absent':
            alerts.append({'type': 'absent', 'message': f"❌ {s['first_name']} {s['last_name']} bugun kelmadi", 'student': s})

    return jsonify(alerts)

# ─── Telegram ─────────────────────────────────────────────────────────────────

@app.route('/api/telegram/send', methods=['POST'])
@login_required
def send_telegram():
    data = request.get_json()
    settings = load_settings()
    token = settings.get('bot_token', '')
    if not token:
        return jsonify({'success': False, 'message': 'Bot token sozlanmagan'})

    target = data.get('target', 'all')  # all / group / student_id
    message = data.get('message', '')
    students = load_json('students.json')

    if target == 'all':
        recipients = [s for s in students if s.get('status') == 'active' and s.get('telegram_chat_id')]
    elif target.startswith('group:'):
        group = target.split(':', 1)[1]
        recipients = [s for s in students if s.get('group') == group and s.get('telegram_chat_id')]
    else:
        recipients = [s for s in students if s['id'] == target and s.get('telegram_chat_id')]

    sent = 0
    failed = 0
    for s in recipients:
        chat_id = s['telegram_chat_id']
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            resp = http_requests.post(url, json={'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}, timeout=5)
            if resp.status_code == 200:
                sent += 1
            else:
                failed += 1
        except:
            failed += 1

    return jsonify({'success': True, 'sent': sent, 'failed': failed})

@app.route('/api/telegram/verify-channel', methods=['POST'])
@login_required
def verify_channel():
    data = request.get_json()
    settings = load_settings()
    token = settings.get('bot_token', '')
    chat_id = data.get('chat_id', '')
    channel = data.get('channel', '')

    if not token:
        return jsonify({'success': False, 'message': 'Bot token sozlanmagan'})

    url = f"https://api.telegram.org/bot{token}/getChatMember"
    try:
        resp = http_requests.post(url, json={'chat_id': channel, 'user_id': chat_id}, timeout=5)
        result = resp.json()
        if result.get('ok'):
            status = result['result']['status']
            is_member = status in ['member', 'administrator', 'creator']
            return jsonify({'success': True, 'is_member': is_member})
    except:
        pass
    return jsonify({'success': False, 'message': 'Tekshirib bo\'lmadi'})

# ─── Settings ─────────────────────────────────────────────────────────────────

@app.route('/settings')
@login_required
def settings_page():
    settings = load_settings()
    return render_template('settings.html', settings=settings, admin_name=session.get('admin_name'))

@app.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    return jsonify(load_settings())

@app.route('/api/settings', methods=['POST'])
@login_required
def update_settings():
    data = request.get_json()
    settings = load_settings()
    for k in ['name', 'currency', 'bot_token', 'required_channels', 'logo']:
        if k in data:
            settings[k] = data[k]
    save_json('settings.json', settings)
    return jsonify({'success': True, 'settings': settings})

@app.route('/api/settings/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json()
    old_pw = data.get('old_password', '')
    new_pw = data.get('new_password', '')

    admins = load_json('admins.json')
    admin = get_admin()
    if not admin:
        return jsonify({'success': False, 'message': 'Admin topilmadi'})

    for i, a in enumerate(admins):
        if a['id'] == admin['id']:
            if a['password'] != hash_password(old_pw):
                return jsonify({'success': False, 'message': 'Eski parol noto\'g\'ri'})
            if len(new_pw) < 6:
                return jsonify({'success': False, 'message': 'Yangi parol kamida 6 ta belgidan iborat bo\'lishi kerak'})
            admins[i]['password'] = hash_password(new_pw)
            save_json('admins.json', admins)
            return jsonify({'success': True})

    return jsonify({'success': False, 'message': 'Xatolik'})

# ─── Image upload ─────────────────────────────────────────────────────────────

@app.route('/api/upload-image', methods=['POST'])
@login_required
def upload_image():
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'Fayl topilmadi'})
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False})

    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
        return jsonify({'success': False, 'message': 'Noto\'g\'ri fayl turi'})

    filename = str(uuid.uuid4())[:16] + '.' + ext
    os.makedirs('static/uploads', exist_ok=True)
    file.save(os.path.join('static/uploads', filename))
    return jsonify({'success': True, 'url': f'/static/uploads/{filename}'})

# ─── Parents section ──────────────────────────────────────────────────────────

@app.route('/parents')
@login_required
def parents_page():
    settings = load_settings()
    return render_template('parents.html', settings=settings, admin_name=session.get('admin_name'))

@app.route('/api/parents')
@login_required
def get_parents():
    students = load_json('students.json')
    parents = {}
    for s in students:
        phone = s.get('parent_phone', '')
        if phone not in parents:
            parents[phone] = {
                'name': s.get('parent_name', ''),
                'phone': phone,
                'children': []
            }
        parents[phone]['children'].append({
            'id': s['id'],
            'name': f"{s['first_name']} {s['last_name']}",
            'group': s.get('group', ''),
            'status': s.get('status', 'active')
        })
    return jsonify(list(parents.values()))

if __name__ == '__main__':
    init_data()
    print("=" * 50)
    print("Smart Kindergarten System")
    print("URL: http://localhost:5000")
    print("Login: 993190712 | Password: 12345678")
    print("=" * 50)
    app.run(debug=True, port=5000)
