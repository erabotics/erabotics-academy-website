"""SuperClass data: schools, staff, classes, students, points, reports, sign-ins, activity log.

Every route checks the caller's role and school on the server (never only in the page):
  admin         any school (must say which with school_id)
  school_admin  their own school only
  teacher       only the classes assigned to them (Live Class and photos)
"""
import json
import re
import time

from . import db, validate
from .superclass import audit, current_user, new_id, public_user, ready, require_origin, USER_SELECT
from .web import ApiError, read_body

DEFAULT_SETTINGS = {'warning_seconds': 5, 'drain_per_second': 1, 'board_text': 'Welcome to class!', 'sounds': True}
RANGES = {'today': 86400, 'week': 7 * 86400, 'month': 30 * 86400, 'term': 120 * 86400, 'all': None}
MAX_PHOTO = 60_000          # characters of the data: URL (the app sends a ~128px JPEG)
BIG_BODY = 400_000          # photos and CSV imports are larger than normal forms
PHOTO_RE = re.compile(r'^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$')


# ---------------------------------------------------------------- access helpers
def _staff(handler, conn):
    user = current_user(handler, conn)
    if user['role'] not in ('admin', 'school_admin'):
        raise ApiError(403, 'Admins only.')
    return user


def _school_id(conn, user, requested):
    """The school this request is about. Platform admins choose; everyone else is fixed to theirs."""
    if user['role'] == 'admin':
        sid = (requested or '').strip()
        if not sid:
            raise ApiError(400, 'Choose a school first.')
    else:
        sid = user['school_id']
        if requested and requested != sid:
            raise ApiError(403, 'You can only manage your own school.')
    if not db.fetch_one(conn, 'SELECT id FROM sc_schools WHERE id = ?', (sid,)):
        raise ApiError(404, 'School not found.')
    return sid


def _class_for(conn, user, class_id, staff_only=False):
    row = db.fetch_one(conn, 'SELECT * FROM sc_classes WHERE id = ?', (class_id,))
    if not row:
        raise ApiError(404, 'Class not found.')
    if user['role'] == 'admin':
        return row
    if row['school_id'] != user['school_id']:
        raise ApiError(403, 'Not your school.')
    if user['role'] == 'teacher':
        if staff_only or not db.fetch_one(conn, 'SELECT 1 AS x FROM sc_class_teachers WHERE class_id = ? AND user_id = ?', (class_id, user['id'])):
            raise ApiError(403, 'This class is not assigned to you.')
    return row


def _marks(items):
    return ', '.join('?' for _ in items)


def _id_list(data, key, max_items=200):
    value = data.get(key, [])
    if not isinstance(value, list) or len(value) > max_items or not all(isinstance(v, str) and 0 < len(v) <= 40 for v in value):
        raise ApiError(400, 'Invalid list.')
    return list(dict.fromkeys(value))


def _int(data, key, lo, hi, default):
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ApiError(400, f'{key.replace("_", " ").capitalize()} must be a number from {lo} to {hi}.')
    return value


def _settings(row):
    try:
        saved = json.loads(row['settings'] or '{}')
    except ValueError:
        saved = {}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in saved.items() if k in DEFAULT_SETTINGS}}


# ---------------------------------------------------------------- schools
def list_schools(handler, query):
    ready()
    with db.connection() as conn:
        user = _staff(handler, conn)
        where, params = ('', ()) if user['role'] == 'admin' else ('WHERE s.id = ?', (user['school_id'],))
        rows = db.fetch_all(conn, f'SELECT s.id, s.name, s.city, s.status, s.created_at FROM sc_schools s {where} ORDER BY s.name', params)
        for r in rows:
            q = lambda sql: db.fetch_one(conn, sql, (r['id'],))['n']
            r['classes'] = q('SELECT COUNT(*) AS n FROM sc_classes WHERE archived = 0 AND school_id = ?')
            r['students'] = q('SELECT COUNT(*) AS n FROM sc_students WHERE active = 1 AND school_id = ?')
            r['staff'] = q("SELECT COUNT(*) AS n FROM sc_users WHERE school_id = ? AND role IN ('teacher', 'school_admin')")
    return 200, {'ok': True, 'schools': rows}, ()


def add_school(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    name = validate.text(data, 'name', 'School name', 80)
    city = validate.text(data, 'city', 'City', 80, required=False)
    with db.connection() as conn:
        user = current_user(handler, conn)
        if user['role'] != 'admin':
            raise ApiError(403, 'Only the platform admin can add schools.')
        if db.fetch_one(conn, 'SELECT id FROM sc_schools WHERE LOWER(name) = ?', (name.lower(),)):
            raise ApiError(409, 'A school with that name already exists.')
        sid = new_id()
        db.execute(conn, 'INSERT INTO sc_schools (id, name, city, created_at) VALUES (?, ?, ?, ?)', (sid, name, city, int(time.time())))
        audit(conn, user, 'school_added', name, school_id=sid)
    return 201, {'ok': True, 'school': {'id': sid, 'name': name, 'city': city, 'status': 'active'}}, ()


def update_school(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    sid = validate.text(data, 'id', 'School', 40)
    name = validate.text(data, 'name', 'School name', 80)
    city = validate.text(data, 'city', 'City', 80, required=False)
    status = validate.choice(data, 'status', 'Status', ('active', 'paused'), 'active')
    with db.connection() as conn:
        user = current_user(handler, conn)
        if user['role'] != 'admin':
            raise ApiError(403, 'Only the platform admin can edit schools.')
        if db.execute(conn, 'UPDATE sc_schools SET name = ?, city = ?, status = ? WHERE id = ?', (name, city, status, sid)).rowcount == 0:
            raise ApiError(404, 'School not found.')
        if status == 'paused':  # everyone at the school is signed out
            db.execute(conn, 'DELETE FROM sc_sessions WHERE user_id IN (SELECT id FROM sc_users WHERE school_id = ?)', (sid,))
        audit(conn, user, 'school_updated', f'{name} ({status})', school_id=sid)
    return 200, {'ok': True}, ()


# ---------------------------------------------------------------- school settings
def get_settings(handler, query):
    ready()
    with db.connection() as conn:
        user = _staff(handler, conn)
        sid = _school_id(conn, user, (query.get('school_id') or [''])[0])
        row = db.fetch_one(conn, 'SELECT settings FROM sc_schools WHERE id = ?', (sid,))
    return 200, {'ok': True, 'settings': _settings(row)}, ()


def update_settings(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    settings = {
        'warning_seconds': _int(data, 'warning_seconds', 3, 30, 5),
        'drain_per_second': _int(data, 'drain_per_second', 1, 5, 1),
        'board_text': validate.text(data, 'board_text', 'Whiteboard text', 60, required=False) or DEFAULT_SETTINGS['board_text'],
        'sounds': data.get('sounds', True) is not False,
    }
    with db.connection() as conn:
        user = _staff(handler, conn)
        sid = _school_id(conn, user, data.get('school_id'))
        db.execute(conn, 'UPDATE sc_schools SET settings = ? WHERE id = ?', (json.dumps(settings), sid))
        audit(conn, user, 'settings_changed', json.dumps(settings), school_id=sid)
    return 200, {'ok': True, 'settings': settings}, ()


# ---------------------------------------------------------------- staff (school admins and teachers)
def _manageable(actor, target):
    """Can `actor` edit this account? Never platform admins; school admins only manage teachers at their school."""
    if target['role'] == 'admin':
        return False
    if actor['role'] == 'admin':
        return True
    return target['school_id'] == actor['school_id'] and target['role'] == 'teacher'


def list_users(handler, query):
    ready()
    with db.connection() as conn:
        user = _staff(handler, conn)
        requested = (query.get('school_id') or [''])[0]
        if user['role'] == 'admin' and not requested:
            rows = db.fetch_all(conn, USER_SELECT + " WHERE u.role <> 'admin' ORDER BY sch.name, u.name")
        else:
            sid = _school_id(conn, user, requested)
            rows = db.fetch_all(conn, USER_SELECT + " WHERE u.role <> 'admin' AND u.school_id = ? ORDER BY u.name", (sid,))
    return 200, {'ok': True, 'users': [public_user(r) for r in rows]}, ()


def add_user(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    name = validate.text(data, 'name', 'Name', 100)
    email = validate.email(data, required=True).lower()
    role = validate.choice(data, 'role', 'Role', ('teacher', 'school_admin'), 'teacher')
    with db.connection() as conn:
        user = _staff(handler, conn)
        sid = _school_id(conn, user, data.get('school_id'))
        if role == 'school_admin' and user['role'] != 'admin':
            raise ApiError(403, 'Only the platform admin can add school admins.')
        if db.fetch_one(conn, 'SELECT id FROM sc_users WHERE email = ?', (email,)):
            raise ApiError(409, 'That email already has an account.')
        uid = new_id()
        db.execute(conn, 'INSERT INTO sc_users (id, email, name, role, school_id, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                   (uid, email, name, role, sid, int(time.time())))
        audit(conn, user, 'user_added', f'{name} <{email}> as {role}', school_id=sid)
        created = db.fetch_one(conn, USER_SELECT + ' WHERE u.id = ?', (uid,))
    return 201, {'ok': True, 'user': public_user(created)}, ()


def update_user(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    uid = validate.text(data, 'id', 'Account', 40)
    name = validate.text(data, 'name', 'Name', 100)
    email = validate.email(data, required=True).lower()
    status = validate.choice(data, 'status', 'Status', ('active', 'paused'), 'active')
    with db.connection() as conn:
        user = _staff(handler, conn)
        target = db.fetch_one(conn, USER_SELECT + ' WHERE u.id = ?', (uid,))
        if not target or not _manageable(user, target):
            raise ApiError(404, 'Account not found.')
        if uid == user['id'] and status != 'active':
            raise ApiError(400, 'You cannot pause your own account.')
        if db.fetch_one(conn, 'SELECT id FROM sc_users WHERE email = ? AND id <> ?', (email, uid)):
            raise ApiError(409, 'That email already has an account.')
        db.execute(conn, 'UPDATE sc_users SET name = ?, email = ?, status = ? WHERE id = ?', (name, email, status, uid))
        if status != 'active':
            db.execute(conn, 'DELETE FROM sc_sessions WHERE user_id = ?', (uid,))
        audit(conn, user, 'user_updated', f'{name} <{email}> ({status})', school_id=target['school_id'])
    return 200, {'ok': True}, ()


def remove_user(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    uid = validate.text(data, 'id', 'Account', 40)
    with db.connection() as conn:
        user = _staff(handler, conn)
        target = db.fetch_one(conn, USER_SELECT + ' WHERE u.id = ?', (uid,))
        if not target or not _manageable(user, target):
            raise ApiError(404, 'Account not found.')
        if uid == user['id']:
            raise ApiError(400, 'You cannot remove your own account.')
        db.execute(conn, 'DELETE FROM sc_class_teachers WHERE user_id = ?', (uid,))
        db.execute(conn, 'DELETE FROM sc_sessions WHERE user_id = ?', (uid,))
        db.execute(conn, 'DELETE FROM sc_users WHERE id = ?', (uid,))
        audit(conn, user, 'user_removed', f"{target['name']} <{target['email']}>", school_id=target['school_id'])
    return 200, {'ok': True}, ()


# ---------------------------------------------------------------- classes
def _teachers_of_school(conn, sid, ids):
    if not ids:
        return []
    rows = db.fetch_all(conn, f"SELECT id FROM sc_users WHERE school_id = ? AND status = 'active' AND id IN ({_marks(ids)})", (sid, *ids))
    if len(rows) != len(ids):
        raise ApiError(400, 'Choose teachers from this school.')
    return ids


def _set_teachers(conn, class_id, ids):
    db.execute(conn, 'DELETE FROM sc_class_teachers WHERE class_id = ?', (class_id,))
    for tid in ids:
        db.execute(conn, 'INSERT INTO sc_class_teachers (class_id, user_id) VALUES (?, ?)', (class_id, tid))


def list_classes(handler, query):
    ready()
    with db.connection() as conn:
        user = current_user(handler, conn)
        requested = (query.get('school_id') or [''])[0]
        if user['role'] == 'teacher':
            classes = db.fetch_all(conn, '''SELECT c.* FROM sc_classes c JOIN sc_class_teachers t ON t.class_id = c.id
                                            WHERE t.user_id = ? AND c.archived = 0 ORDER BY c.name''', (user['id'],))
        else:
            sid = _school_id(conn, user, requested)
            classes = db.fetch_all(conn, 'SELECT * FROM sc_classes WHERE school_id = ? ORDER BY archived, name', (sid,))
        ids = [c['id'] for c in classes]
        teachers, counts = {}, {}
        if ids:
            for r in db.fetch_all(conn, f'''SELECT t.class_id, u.id, u.name FROM sc_class_teachers t JOIN sc_users u ON u.id = t.user_id
                                            WHERE t.class_id IN ({_marks(ids)}) ORDER BY u.name''', ids):
                teachers.setdefault(r['class_id'], []).append({'id': r['id'], 'name': r['name']})
            for r in db.fetch_all(conn, f'''SELECT e.class_id, COUNT(*) AS n FROM sc_enrollments e JOIN sc_students s ON s.id = e.student_id
                                            WHERE s.active = 1 AND e.class_id IN ({_marks(ids)}) GROUP BY e.class_id''', ids):
                counts[r['class_id']] = r['n']
    out = [{'id': c['id'], 'schoolId': c['school_id'], 'name': c['name'], 'level': c['level'], 'schedule': c['schedule'],
            'archived': bool(c['archived']), 'teachers': teachers.get(c['id'], []), 'studentCount': counts.get(c['id'], 0)} for c in classes]
    return 200, {'ok': True, 'classes': out}, ()


def _class_fields(data):
    return (validate.text(data, 'name', 'Class name', 80), validate.text(data, 'level', 'Level', 60, required=False),
            validate.text(data, 'schedule', 'Schedule', 80, required=False))


def add_class(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    name, level, schedule = _class_fields(data)
    teacher_ids = _id_list(data, 'teacher_ids', 30)
    with db.connection() as conn:
        user = _staff(handler, conn)
        sid = _school_id(conn, user, data.get('school_id'))
        _teachers_of_school(conn, sid, teacher_ids)
        cid = new_id()
        db.execute(conn, 'INSERT INTO sc_classes (id, school_id, name, level, schedule, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                   (cid, sid, name, level, schedule, int(time.time())))
        _set_teachers(conn, cid, teacher_ids)
        audit(conn, user, 'class_added', name, school_id=sid)
    return 201, {'ok': True, 'id': cid}, ()


def update_class(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    cid = validate.text(data, 'id', 'Class', 40)
    name, level, schedule = _class_fields(data)
    with db.connection() as conn:
        user = _staff(handler, conn)
        row = _class_for(conn, user, cid, staff_only=True)
        archived = 1 if data.get('archived') is True else 0
        db.execute(conn, 'UPDATE sc_classes SET name = ?, level = ?, schedule = ?, archived = ? WHERE id = ?', (name, level, schedule, archived, cid))
        if 'teacher_ids' in data:
            _set_teachers(conn, cid, _teachers_of_school(conn, row['school_id'], _id_list(data, 'teacher_ids', 30)))
        audit(conn, user, 'class_updated', f'{name}{" (archived)" if archived else ""}', school_id=row['school_id'])
    return 200, {'ok': True}, ()


# ---------------------------------------------------------------- students
def _enroll(conn, school_id, student_id, class_ids):
    """Replace a student's classes with `class_ids` (all must belong to the school)."""
    if class_ids:
        found = db.fetch_all(conn, f'SELECT id FROM sc_classes WHERE school_id = ? AND id IN ({_marks(class_ids)})', (school_id, *class_ids))
        if len(found) != len(class_ids):
            raise ApiError(400, 'Choose classes from this school.')
    db.execute(conn, 'DELETE FROM sc_enrollments WHERE student_id = ?', (student_id,))
    for cid in class_ids:
        db.execute(conn, 'INSERT INTO sc_enrollments (class_id, student_id) VALUES (?, ?)', (cid, student_id))


def _photo(data):
    photo = data.get('photo', '')
    if photo in ('', None):
        return ''
    if not isinstance(photo, str) or len(photo) > MAX_PHOTO or not PHOTO_RE.match(photo):
        raise ApiError(400, 'Photo is invalid or too large.')
    return photo


def list_students(handler, query):
    ready()
    with db.connection() as conn:
        user = current_user(handler, conn)
        class_id = (query.get('class_id') or [''])[0]
        if class_id:
            sid = _class_for(conn, user, class_id)['school_id']
            students = db.fetch_all(conn, '''SELECT s.id, s.name, s.active, s.photo FROM sc_students s JOIN sc_enrollments e ON e.student_id = s.id
                                             WHERE e.class_id = ? ORDER BY s.name''', (class_id,))
        elif user['role'] == 'teacher':
            raise ApiError(400, 'Choose a class.')
        else:
            sid = _school_id(conn, user, (query.get('school_id') or [''])[0])
            students = db.fetch_all(conn, 'SELECT id, name, active, photo FROM sc_students WHERE school_id = ? ORDER BY name', (sid,))
        classes = {}
        for r in db.fetch_all(conn, '''SELECT e.student_id, e.class_id FROM sc_enrollments e JOIN sc_classes c ON c.id = e.class_id
                                       WHERE c.school_id = ?''', (sid,)):
            classes.setdefault(r['student_id'], []).append(r['class_id'])
    out = [{'id': s['id'], 'name': s['name'], 'active': bool(s['active']), 'hasPhoto': bool(s['photo']),
            'classIds': classes.get(s['id'], [])} for s in students]
    return 200, {'ok': True, 'students': out}, ()


def add_student(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    name = validate.text(data, 'name', 'Student name', 100)
    class_ids = _id_list(data, 'class_ids', 30)
    with db.connection() as conn:
        user = _staff(handler, conn)
        sid = _school_id(conn, user, data.get('school_id'))
        stid = new_id()
        db.execute(conn, 'INSERT INTO sc_students (id, school_id, name, created_at) VALUES (?, ?, ?, ?)', (stid, sid, name, int(time.time())))
        _enroll(conn, sid, stid, class_ids)
        audit(conn, user, 'student_added', name, school_id=sid)
    return 201, {'ok': True, 'id': stid}, ()


def update_student(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True, max_body=BIG_BODY)
    stid = validate.text(data, 'id', 'Student', 40)
    name = validate.text(data, 'name', 'Student name', 100)
    with db.connection() as conn:
        user = _staff(handler, conn)
        st = db.fetch_one(conn, 'SELECT * FROM sc_students WHERE id = ?', (stid,))
        if not st or (user['role'] != 'admin' and st['school_id'] != user['school_id']):
            raise ApiError(404, 'Student not found.')
        active = 0 if data.get('active') is False else 1
        photo = _photo(data) if 'photo' in data else st['photo']
        db.execute(conn, 'UPDATE sc_students SET name = ?, active = ?, photo = ? WHERE id = ?', (name, active, photo, stid))
        if 'class_ids' in data:
            _enroll(conn, st['school_id'], stid, _id_list(data, 'class_ids', 30))
        audit(conn, user, 'student_updated', f'{name}{"" if active else " (archived)"}', school_id=st['school_id'])
    return 200, {'ok': True}, ()


def remove_student(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    stid = validate.text(data, 'id', 'Student', 40)
    with db.connection() as conn:
        user = _staff(handler, conn)
        st = db.fetch_one(conn, 'SELECT * FROM sc_students WHERE id = ?', (stid,))
        if not st or (user['role'] != 'admin' and st['school_id'] != user['school_id']):
            raise ApiError(404, 'Student not found.')
        for table in ('sc_enrollments', 'sc_points'):
            db.execute(conn, f'DELETE FROM {table} WHERE student_id = ?', (stid,))  # fixed internal names
        db.execute(conn, 'DELETE FROM sc_students WHERE id = ?', (stid,))
        audit(conn, user, 'student_removed', st['name'], school_id=st['school_id'])
    return 200, {'ok': True}, ()


def student_photo(handler, query):
    """A teacher (or admin) sets the photo of a student in one of their classes."""
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True, max_body=BIG_BODY)
    stid = validate.text(data, 'id', 'Student', 40)
    photo = _photo(data)
    with db.connection() as conn:
        user = current_user(handler, conn)
        st = db.fetch_one(conn, 'SELECT * FROM sc_students WHERE id = ?', (stid,))
        if not st or (user['role'] != 'admin' and st['school_id'] != user['school_id']):
            raise ApiError(404, 'Student not found.')
        if user['role'] == 'teacher' and not db.fetch_one(conn, '''SELECT 1 AS x FROM sc_enrollments e JOIN sc_class_teachers t ON t.class_id = e.class_id
                                                                   WHERE e.student_id = ? AND t.user_id = ?''', (stid, user['id'])):
            raise ApiError(403, 'This student is not in your class.')
        db.execute(conn, 'UPDATE sc_students SET photo = ? WHERE id = ?', (photo, stid))
    return 200, {'ok': True}, ()


def import_students(handler, query):
    """Bulk add from a list of names (the page reads the CSV). Existing names are enrolled, not duplicated."""
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True, max_body=BIG_BODY)
    names = data.get('names')
    if not isinstance(names, list) or not 0 < len(names) <= 500:
        raise ApiError(400, 'Add between 1 and 500 names.')
    clean = []
    for n in names:
        if not isinstance(n, str):
            raise ApiError(400, 'Invalid name list.')
        n = ' '.join(validate.CONTROL_RE.sub('', n).split())
        if n:
            if len(n) > 100:
                raise ApiError(400, f'Name too long: {n[:30]}…')
            clean.append(n)
    with db.connection() as conn:
        user = _staff(handler, conn)
        sid = _school_id(conn, user, data.get('school_id'))
        class_id = data.get('class_id') or ''
        if class_id:
            _class_for(conn, user, class_id, staff_only=True)
        existing = {r['name'].lower(): r['id'] for r in db.fetch_all(conn, 'SELECT id, name FROM sc_students WHERE school_id = ?', (sid,))}
        created = enrolled = 0
        now = int(time.time())
        for n in clean:
            stid = existing.get(n.lower())
            if not stid:
                stid = new_id()
                db.execute(conn, 'INSERT INTO sc_students (id, school_id, name, created_at) VALUES (?, ?, ?, ?)', (stid, sid, n, now))
                existing[n.lower()] = stid
                created += 1
            if class_id and not db.fetch_one(conn, 'SELECT 1 AS x FROM sc_enrollments WHERE class_id = ? AND student_id = ?', (class_id, stid)):
                db.execute(conn, 'INSERT INTO sc_enrollments (class_id, student_id) VALUES (?, ?)', (class_id, stid))
                enrolled += 1
        audit(conn, user, 'students_imported', f'{created} new, {enrolled} enrolled', school_id=sid)
    return 200, {'ok': True, 'created': created, 'enrolled': enrolled}, ()


# ---------------------------------------------------------------- Live Class and points
def live(handler, query):
    ready()
    class_id = (query.get('class_id') or [''])[0]
    with db.connection() as conn:
        user = current_user(handler, conn)
        cls = _class_for(conn, user, class_id)
        school = db.fetch_one(conn, 'SELECT settings FROM sc_schools WHERE id = ?', (cls['school_id'],))
        rows = db.fetch_all(conn, '''SELECT s.id, s.name, s.photo, COALESCE(SUM(p.delta), 0) AS points
                                     FROM sc_students s JOIN sc_enrollments e ON e.student_id = s.id AND e.class_id = ?
                                     LEFT JOIN sc_points p ON p.student_id = s.id AND p.class_id = ? AND p.undone = 0
                                     WHERE s.active = 1 GROUP BY s.id, s.name, s.photo ORDER BY s.name''', (class_id, class_id))
    students = [{'id': r['id'], 'name': r['name'], 'photo': r['photo'], 'points': int(r['points'])} for r in rows]
    return 200, {'ok': True, 'class': {'id': cls['id'], 'name': cls['name'], 'level': cls['level']},
                 'settings': _settings(school), 'students': students}, ()


def save_points(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True, max_body=BIG_BODY)
    class_id = validate.text(data, 'class_id', 'Class', 40)
    changes = data.get('changes')
    if not isinstance(changes, list) or not 0 < len(changes) <= 300:
        raise ApiError(400, 'Nothing to save.')
    with db.connection() as conn:
        user = current_user(handler, conn)
        cls = _class_for(conn, user, class_id)
        enrolled = {r['student_id'] for r in db.fetch_all(conn, 'SELECT student_id FROM sc_enrollments WHERE class_id = ?', (class_id,))}
        now = int(time.time())
        for c in changes:
            if not isinstance(c, dict):
                raise ApiError(400, 'Invalid change.')
            delta = c.get('delta')
            reason = c.get('reason') if c.get('reason') in ('manual', 'warning', 'bonus') else 'manual'
            if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0 or abs(delta) > 50:
                raise ApiError(400, 'Invalid points.')
            if c.get('student_id') not in enrolled:
                raise ApiError(400, 'A student is not in this class.')
            db.execute(conn, 'INSERT INTO sc_points (id, school_id, class_id, student_id, delta, reason, by_user, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (new_id(), cls['school_id'], class_id, c['student_id'], delta, reason, user['id'], now))
    return 200, {'ok': True, 'saved': len(changes)}, ()


def points_history(handler, query):
    ready()
    with db.connection() as conn:
        user = _staff(handler, conn)
        sid = _school_id(conn, user, (query.get('school_id') or [''])[0])
        sql = '''SELECT p.id, p.delta, p.reason, p.at, p.undone, st.name AS student, c.name AS class_name, u.name AS by_name
                 FROM sc_points p JOIN sc_students st ON st.id = p.student_id JOIN sc_classes c ON c.id = p.class_id
                 LEFT JOIN sc_users u ON u.id = p.by_user WHERE p.school_id = ?'''
        params = [sid]
        for key, col in (('class_id', 'p.class_id'), ('student_id', 'p.student_id')):
            value = (query.get(key) or [''])[0]
            if value:
                sql += f' AND {col} = ?'  # fixed column names
                params.append(value)
        rows = db.fetch_all(conn, sql + ' ORDER BY p.at DESC LIMIT 200', params)
    for r in rows:
        r['undone'] = bool(r['undone'])
    return 200, {'ok': True, 'events': rows}, ()


def undo_points(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    pid = validate.text(data, 'id', 'Entry', 40)
    with db.connection() as conn:
        user = _staff(handler, conn)
        row = db.fetch_one(conn, 'SELECT * FROM sc_points WHERE id = ?', (pid,))
        if not row or (user['role'] != 'admin' and row['school_id'] != user['school_id']):
            raise ApiError(404, 'Entry not found.')
        db.execute(conn, 'UPDATE sc_points SET undone = 1 WHERE id = ?', (pid,))
        audit(conn, user, 'points_undone', f"{row['delta']:+d}", school_id=row['school_id'])
    return 200, {'ok': True}, ()


# ---------------------------------------------------------------- reports
def reports(handler, query):
    ready()
    rng = (query.get('range') or ['week'])[0]
    if rng not in RANGES:
        raise ApiError(400, 'Invalid range.')
    with db.connection() as conn:
        user = _staff(handler, conn)
        sid = _school_id(conn, user, (query.get('school_id') or [''])[0])
        since = 0 if RANGES[rng] is None else int(time.time()) - RANGES[rng]
        base = 'FROM sc_points p JOIN sc_students st ON st.id = p.student_id JOIN sc_classes c ON c.id = p.class_id WHERE p.school_id = ? AND p.undone = 0 AND p.at >= ?'
        params = [sid, since]
        class_id = (query.get('class_id') or [''])[0]
        if class_id:
            base += ' AND p.class_id = ?'
            params.append(class_id)
        agg = 'SUM(CASE WHEN p.delta > 0 THEN p.delta ELSE 0 END) AS earned, SUM(CASE WHEN p.delta < 0 THEN -p.delta ELSE 0 END) AS lost, SUM(p.delta) AS net'
        students = db.fetch_all(conn, f'SELECT st.id, st.name, {agg} {base} GROUP BY st.id, st.name ORDER BY net DESC, st.name LIMIT 200', params)
        classes = db.fetch_all(conn, f'SELECT c.id, c.name, {agg} {base} GROUP BY c.id, c.name ORDER BY net DESC', params)
        totals = db.fetch_one(conn, f'SELECT COUNT(*) AS events, COALESCE(SUM(CASE WHEN p.delta > 0 THEN p.delta ELSE 0 END), 0) AS earned, '
                                    f'COALESCE(SUM(CASE WHEN p.delta < 0 THEN -p.delta ELSE 0 END), 0) AS lost {base}', params)
    clean = lambda rows: [{**r, 'earned': int(r['earned'] or 0), 'lost': int(r['lost'] or 0), 'net': int(r['net'] or 0)} for r in rows]
    return 200, {'ok': True, 'range': rng, 'students': clean(students), 'classes': clean(classes),
                 'totals': {k: int(v) for k, v in totals.items()}}, ()


# ---------------------------------------------------------------- active sign-ins
def list_sessions(handler, query):
    ready()
    with db.connection() as conn:
        user = _staff(handler, conn)
        requested = (query.get('school_id') or [''])[0]
        where, params = '', []
        if user['role'] != 'admin' or requested:
            where, params = 'AND u.school_id = ?', [_school_id(conn, user, requested)]
        rows = db.fetch_all(conn, f'''SELECT s.token_hash, s.kind, s.created_at, s.expires_at, u.id AS user_id, u.name, u.email, sch.name AS school_name
                                      FROM sc_sessions s JOIN sc_users u ON u.id = s.user_id LEFT JOIN sc_schools sch ON sch.id = u.school_id
                                      WHERE s.expires_at > ? {where} ORDER BY s.created_at DESC LIMIT 200''', [int(time.time()), *params])
    out = [{'id': r['token_hash'][:16], 'kind': r['kind'], 'createdAt': r['created_at'], 'expiresAt': r['expires_at'],
            'userId': r['user_id'], 'name': r['name'], 'email': r['email'], 'school': r['school_name']} for r in rows]
    return 200, {'ok': True, 'sessions': out}, ()


def revoke_sessions(handler, query):
    """Sign one device out (session_id) or a person out everywhere (user_id)."""
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    with db.connection() as conn:
        user = _staff(handler, conn)
        if data.get('session_id'):
            sid16 = validate.text(data, 'session_id', 'Session', 16)
            row = db.fetch_one(conn, USER_SELECT.replace('FROM sc_users u', 'FROM sc_sessions s JOIN sc_users u ON u.id = s.user_id')
                               + ' WHERE s.token_hash LIKE ?', (sid16 + '%',))
            target_id = row['id'] if row else None
        else:
            target_id = validate.text(data, 'user_id', 'Account', 40)
            row = db.fetch_one(conn, USER_SELECT + ' WHERE u.id = ?', (target_id,))
        if not row or (user['role'] != 'admin' and row['school_id'] != user['school_id']):
            raise ApiError(404, 'Sign-in not found.')
        if data.get('session_id'):
            db.execute(conn, 'DELETE FROM sc_sessions WHERE token_hash LIKE ? AND user_id = ?', (sid16 + '%', target_id))
        else:
            db.execute(conn, 'DELETE FROM sc_sessions WHERE user_id = ?', (target_id,))
        audit(conn, user, 'signed_out', row['name'], school_id=row['school_id'])
    return 200, {'ok': True}, ()


# ---------------------------------------------------------------- activity log
def activity(handler, query):
    ready()
    with db.connection() as conn:
        user = _staff(handler, conn)
        requested = (query.get('school_id') or [''])[0]
        if user['role'] == 'admin' and not requested:
            rows = db.fetch_all(conn, 'SELECT a.*, sch.name AS school_name FROM sc_audit a LEFT JOIN sc_schools sch ON sch.id = a.school_id ORDER BY a.at DESC LIMIT 200')
        else:
            sid = _school_id(conn, user, requested)
            rows = db.fetch_all(conn, 'SELECT a.*, sch.name AS school_name FROM sc_audit a LEFT JOIN sc_schools sch ON sch.id = a.school_id '
                                      'WHERE a.school_id = ? ORDER BY a.at DESC LIMIT 200', (sid,))
    out = [{'id': r['id'], 'at': r['at'], 'user': r['user_name'], 'action': r['action'], 'detail': r['detail'], 'school': r['school_name']} for r in rows]
    return 200, {'ok': True, 'events': out}, ()


ROUTES = {
    ('GET', 'schools'): list_schools, ('POST', 'schools'): add_school, ('POST', 'schools/update'): update_school,
    ('GET', 'settings'): get_settings, ('POST', 'settings/update'): update_settings,
    ('GET', 'users'): list_users, ('POST', 'users'): add_user, ('POST', 'users/update'): update_user, ('POST', 'users/remove'): remove_user,
    ('GET', 'classes'): list_classes, ('POST', 'classes'): add_class, ('POST', 'classes/update'): update_class,
    ('GET', 'students'): list_students, ('POST', 'students'): add_student, ('POST', 'students/update'): update_student,
    ('POST', 'students/remove'): remove_student, ('POST', 'students/photo'): student_photo, ('POST', 'students/import'): import_students,
    ('GET', 'live'): live, ('POST', 'points'): save_points, ('GET', 'points'): points_history, ('POST', 'points/undo'): undo_points,
    ('GET', 'reports'): reports,
    ('GET', 'sessions'): list_sessions, ('POST', 'sessions/revoke'): revoke_sessions,
    ('GET', 'activity'): activity,
}
