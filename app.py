
import streamlit as st
import sqlite3
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ==========================================
# 1. 기본 설정
# ==========================================

st.set_page_config(
    page_title="STUDY HUB",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed"
)

KST = ZoneInfo("Asia/Seoul")

# 새 데이터베이스 파일 사용
DB_PATH = os.environ.get(
    "STUDY_HUB_DB",
    "/tmp/study_hub_v2.db"
)

ADMIN_PASSWORD = os.environ.get(
    "STUDY_HUB_ADMIN_PASSWORD",
    "studyhub1234"
)

CLOSING_HOUR = 22

DURATION_OPTIONS = {
    "1시간": 1,
    "2시간": 2,
    "3시간": 3,
    "4시간": 4
}

ROOMS = {
    "3층 A실": [f"A{i:02d}" for i in range(1, 31)],
    "3층 B실": [f"B{i:02d}" for i in range(1, 31)],
    "4층 C실": [f"C{i:02d}" for i in range(1, 61)]
}

TOTAL_SEATS = 120


# ==========================================
# 2. 현재 시각 계산
# ==========================================

def get_now():
    return datetime.now(KST).replace(
        second=0,
        microsecond=0
    )


def get_current_period(hours):
    start = get_now()
    end = start + timedelta(hours=hours)
    return start, end


def format_datetime(value):
    return value.strftime("%Y-%m-%d %H:%M")


def check_operating_hours(start, end):
    closing = start.replace(
        hour=CLOSING_HOUR,
        minute=0,
        second=0,
        microsecond=0
    )

    return end <= closing


def time_remaining(end):
    now = get_now()
    seconds = max(
        0,
        int((end - now).total_seconds())
    )

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    return f"{hours}시간 {minutes}분"


# ==========================================
# 3. 화면 디자인
# ==========================================

st.markdown("""
<style>

@import url(
'https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap'
);

html, body, [class*="css"] {
    font-family: 'Noto Sans KR', sans-serif;
}

.stApp {
    background-color: #F5F7FB;
}

.main-title {
    font-size: 38px;
    font-weight: 800;
    color: #172554;
    letter-spacing: -1.5px;
}

.sub-title {
    color: #64748B;
    font-size: 14px;
}

.login-card {
    background: white;
    padding: 28px;
    border-radius: 18px;
    border: 1px solid #E2E8F0;
}

section[data-testid="stSidebar"] {
    background-color: #172554;
}

section[data-testid="stSidebar"] * {
    color: white;
}

/* 입력창 배경과 글씨 */

.stTextInput input {
    background-color: white !important;
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
    border: 1px solid #CBD5E1 !important;
}

.stTextInput input::placeholder {
    color: #94A3B8 !important;
    -webkit-text-fill-color: #94A3B8 !important;
}

.stTextInput input:focus {
    border: 2px solid #2563EB !important;
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
}

/* 버튼 */

div.stButton > button {
    border-radius: 10px;
    font-weight: 600;
    min-height: 42px;
}

h1, h2, h3 {
    color: #172554;
}

</style>
""", unsafe_allow_html=True)


# ==========================================
# 4. 데이터베이스 연결
# ==========================================

def get_connection():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=20,
        check_same_thread=False
    )

    conn.execute("PRAGMA busy_timeout = 20000")

    return conn


def init_database():

    with get_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reservations (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                student_id TEXT NOT NULL,

                student_name TEXT NOT NULL,

                room TEXT NOT NULL,

                seat TEXT NOT NULL,

                start_time TEXT NOT NULL,

                end_time TEXT NOT NULL,

                created_at TEXT NOT NULL

            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reservation_time
            ON reservations(start_time, end_time)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reservation_user
            ON reservations(student_id)
        """)


init_database()


# ==========================================
# 5. 예약 시간 중복 확인
# ==========================================

def get_overlapping_reservations(
    room,
    seat,
    start_time,
    end_time
):

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT id, start_time, end_time
            FROM reservations

            WHERE room = ?
            AND seat = ?

            AND start_time < ?
            AND end_time > ?

        """, (
            room,
            seat,
            format_datetime(end_time),
            format_datetime(start_time)
        )).fetchall()

    return rows


def get_booked_seats(start_time, end_time, room):

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT DISTINCT seat
            FROM reservations

            WHERE room = ?
            AND start_time < ?
            AND end_time > ?

        """, (
            room,
            format_datetime(end_time),
            format_datetime(start_time)
        )).fetchall()

    return {row[0] for row in rows}


# ==========================================
# 6. 예약 생성
# ==========================================

def make_reservation(
    student_id,
    student_name,
    room,
    seat,
    start_time,
    end_time
):

    if room not in ROOMS or seat not in ROOMS[room]:
        return False, "올바르지 않은 좌석입니다."

    # 운영시간 검사
    if not check_operating_hours(start_time, end_time):
        return False, "자습실은 오후 10시까지만 운영합니다."

    # 이미 지나간 예약 방지
    if start_time < get_now():
        return False, "예약 시작 시간이 지났습니다. 다시 시도해 주세요."

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        # 좌석 중복 예약 확인
        existing_seat = conn.execute("""
            SELECT id
            FROM reservations

            WHERE room = ?
            AND seat = ?

            AND start_time < ?
            AND end_time > ?

            LIMIT 1

        """, (
            room,
            seat,
            format_datetime(end_time),
            format_datetime(start_time)
        )).fetchone()

        if existing_seat:

            conn.rollback()

            return False, "해당 시간에 이미 예약된 좌석입니다."

        # 같은 학생의 시간 중복 예약 방지
        existing_user = conn.execute("""
            SELECT id
            FROM reservations

            WHERE student_id = ?

            AND start_time < ?
            AND end_time > ?

            LIMIT 1

        """, (
            student_id,
            format_datetime(end_time),
            format_datetime(start_time)
        )).fetchone()

        if existing_user:

            conn.rollback()

            return False, "해당 시간에 이미 다른 좌석을 예약했습니다."

        # 예약 저장
        conn.execute("""
            INSERT INTO reservations (
                student_id,
                student_name,
                room,
                seat,
                start_time,
                end_time,
                created_at
            )

            VALUES (?, ?, ?, ?, ?, ?, ?)

        """, (
            student_id,
            student_name,
            room,
            seat,
            format_datetime(start_time),
            format_datetime(end_time),
            format_datetime(get_now())
        ))

        conn.commit()

        return True, "예약이 성공적으로 완료되었습니다!"

    except sqlite3.Error:

        conn.rollback()

        return False, "데이터베이스 오류가 발생했습니다."

    finally:

        conn.close()

# ==========================================
# 7. 내 예약 조회 및 취소
# ==========================================

def get_my_reservations(student_id):

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT
                id,
                room,
                seat,
                start_time,
                end_time

            FROM reservations

            WHERE student_id = ?

            ORDER BY start_time

        """, (student_id,)).fetchall()

    return rows


def cancel_reservation(reservation_id, student_id):

    with get_connection() as conn:

        result = conn.execute("""
            DELETE FROM reservations

            WHERE id = ?
            AND student_id = ?

        """, (
            reservation_id,
            student_id
        ))

    return result.rowcount > 0


# ==========================================
# 8. 로그인 상태 관리
# ==========================================

if "user" not in st.session_state:
    st.session_state.user = None

if "selected_seat" not in st.session_state:
    st.session_state.selected_seat = None

if "selection_key" not in st.session_state:
    st.session_state.selection_key = None


# ==========================================
# 9. 로그인 화면
# ==========================================

if st.session_state.user is None:

    st.markdown("<br><br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.5, 1])

    with col2:

        st.markdown(
            '<div class="main-title">📚 STUDY HUB</div>',
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="sub-title">'
            'SMART STUDY ROOM RESERVATION SYSTEM'
            '</div>',
            unsafe_allow_html=True
        )

        st.write("")
        st.divider()

        st.markdown("### 로그인")

        st.write(
            "이름과 학번을 입력하고 자습실 예약을 시작하세요."
        )

        with st.form("login_form"):

            student_name = st.text_input(
                "이름",
                placeholder="이름을 입력하세요",
                max_chars=20
            )

            student_id = st.text_input(
                "학번",
                placeholder="학번을 입력하세요",
                max_chars=20
            )

            login_button = st.form_submit_button(
                "로그인",
                type="primary",
                use_container_width=True
            )

            if login_button:

                student_name = student_name.strip()
                student_id = student_id.strip()

                if not student_name or not student_id:

                    st.error(
                        "이름과 학번을 모두 입력해 주세요."
                    )

                elif len(student_id) < 2:

                    st.error(
                        "학번을 올바르게 입력해 주세요."
                    )

                else:

                    st.session_state.user = {
                        "name": student_name,
                        "id": student_id
                    }

                    st.session_state.selected_seat = None

                    st.rerun()

        st.divider()

        st.caption(
            "STUDY HUB | 스마트 자습실 예약 시스템"
        )

    st.stop()


# ==========================================
# 10. 로그인 이후 사이드바
# ==========================================

with st.sidebar:

    st.markdown("# 📚 STUDY HUB")

    st.divider()

    st.success(
        f"{st.session_state.user['name']}님 환영합니다!"
    )

    st.write(
        f"학번: {st.session_state.user['id']}"
    )

    if st.button(
        "로그아웃",
        use_container_width=True
    ):

        st.session_state.user = None
        st.session_state.selected_seat = None

        st.rerun()

    st.divider()

    st.markdown("### 🏫 자습실 안내")

    st.markdown("""
    **3층**
    - A실 : 30석
    - B실 : 30석

    **4층**
    - C실 : 60석

    **전체 120석**
    """)

    st.divider()

    st.markdown("### ⏰ 운영시간")

    st.write("매일 오후 10시까지")


# ==========================================
# 11. 메인 홈페이지
# ==========================================

st.markdown(
    '<div class="main-title">STUDY HUB</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-title">'
    '스마트 자습실 좌석 예약 시스템'
    '</div>',
    unsafe_allow_html=True
)

st.write("")

# 현재 시각 표시

current_time = get_now()

st.info(
    f"🕒 현재 한국 시각: {current_time.strftime('%Y년 %m월 %d일 %H:%M')}"
)

# 메뉴

tab1, tab2, tab3 = st.tabs([
    "🪑 좌석 예약",
    "📋 내 예약",
    "📊 전체 현황"
])


# ==========================================
# 12. 좌석 예약
# ==========================================

with tab1:

    st.header("🪑 자습실 좌석 예약")

    st.caption(
        "현재 시각부터 원하는 시간만큼 이용할 수 있습니다."
    )

    # 현재 시각 기준 이용 시간 계산

    selected_duration_label = st.radio(
        "이용 시간을 선택하세요.",
        list(DURATION_OPTIONS.keys()),
        horizontal=True
    )

    selected_duration = DURATION_OPTIONS[
        selected_duration_label
    ]

    start_time, end_time = get_current_period(
        selected_duration
    )

    st.divider()

    # 예약 시간 표시

    col1, col2 = st.columns(2)

    with col1:

        st.metric(
            "예약 시작",
            start_time.strftime("%H:%M")
        )

    with col2:

        st.metric(
            "예약 종료 예정",
            end_time.strftime("%H:%M")
        )

    st.write("")

    # 운영 종료 시간 확인

    if not check_operating_hours(start_time, end_time):

        st.error(
            "⏰ 예약할 수 없습니다!\n\n"
            "자습실은 오후 10시까지만 운영합니다. "
            "선택한 이용 시간이 운영 종료 시간을 초과합니다. "
            "이용 시간을 줄여 다시 선택해 주세요."
        )

        closing_time = start_time.replace(
            hour=22,
            minute=0,
            second=0,
            microsecond=0
        )

        remaining_minutes = max(
            0,
            int((closing_time - start_time).total_seconds() // 60)
        )

        st.warning(
            f"현재 이용 가능한 시간은 최대 "
            f"{remaining_minutes}분입니다."
        )

    else:

        st.success(
            f"예약 가능 시간: "
            f"{start_time.strftime('%H:%M')} ~ "
            f"{end_time.strftime('%H:%M')}"
        )

    st.divider()

    # 자습실 선택

    selected_room = st.selectbox(
        "🏫 자습실을 선택하세요.",
        list(ROOMS.keys())
    )

    # 예약된 좌석 조회

    booked_seats = get_booked_seats(
        start_time,
        end_time,
        selected_room
    )

    all_seats = ROOMS[selected_room]

    available_count = (
        len(all_seats) - len(booked_seats)
    )

    # 좌석 통계

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "전체 좌석",
        f"{len(all_seats)}석"
    )

    c2.metric(
        "예약 완료",
        f"{len(booked_seats)}석"
    )

    c3.metric(
        "예약 가능",
        f"{available_count}석"
    )

    st.divider()

    # 좌석 배치도

    st.markdown("### 좌석 배치도")

    st.markdown("""
    <div style="
        text-align:center;
        background:#DBEAFE;
        padding:12px;
        border-radius:10px;
        color:#1E40AF;
        font-weight:bold;
        margin-bottom:20px;
    ">
        📍 앞쪽 / 칠판
    </div>
    """, unsafe_allow_html=True)

    st.caption(
        "🟢 예약 가능  |  🔴 예약 완료  |  🔵 선택한 좌석"
    )

    # 자습실이나 이용 시간이 바뀌면 선택 초기화

    selection_key = (
        selected_room,
        selected_duration_label,
        start_time.strftime("%Y-%m-%d %H:%M")
    )

    if st.session_state.selection_key != selection_key:

        st.session_state.selected_seat = None

        st.session_state.selection_key = selection_key

    # 좌석 버튼 생성

    columns = st.columns(5)

    for index, seat in enumerate(all_seats):

        with columns[index % 5]:

            is_booked = seat in booked_seats

            is_selected = (
                st.session_state.selected_seat == seat
            )

            if is_booked:

                label = f"🔴 {seat}"
                disabled = True
                button_type = "secondary"

            elif is_selected:

                label = f"🔵 {seat}"
                disabled = False
                button_type = "primary"

            else:

                label = f"🟢 {seat}"
                disabled = False
                button_type = "secondary"

            if st.button(
                label,
                key=f"seat_{selected_room}_{seat}",
                disabled=disabled,
                type=button_type,
                use_container_width=True
            ):

                st.session_state.selected_seat = seat

                st.rerun()

    st.divider()

    # 예약 최종 확인

    st.markdown("### 예약 정보 확인")

    if st.session_state.selected_seat:

        st.info(
            f"""
**예약자:** {st.session_state.user['name']}

**자습실:** {selected_room}

**좌석:** {st.session_state.selected_seat}

**시작 시간:** {format_datetime(start_time)}

**종료 시간:** {format_datetime(end_time)}

**이용 시간:** {selected_duration}시간
"""
        )

        if not check_operating_hours(start_time, end_time):

            st.error(
                "운영 종료 시간을 초과하여 예약할 수 없습니다."
            )

        else:

            if st.button(
                "✅ 예약 확정하기",
                type="primary",
                use_container_width=True
            ):

                # 버튼을 누르는 순간 다시 현재 시각 계산

                latest_start, latest_end = get_current_period(
                    selected_duration
                )

                if not check_operating_hours(
                    latest_start,
                    latest_end
                ):

                    st.error(
                        "오후 10시 운영 종료 시간을 초과했습니다. "
                        "이용 시간을 줄여 주세요."
                    )

                else:

                    success, message = make_reservation(
                        st.session_state.user["id"],
                        st.session_state.user["name"],
                        selected_room,
                        st.session_state.selected_seat,
                        latest_start,
                        latest_end
                    )

                    if success:

                        st.session_state.selected_seat = None

                        st.success(message)

                        st.balloons()

                        st.rerun()

                    else:

                        st.error(message)

    else:

        st.warning(
            "예약할 좌석을 먼저 선택해 주세요."
        )

# ==========================================
# 13. 내 예약 내역
# ==========================================

with tab2:

    st.header("📋 내 예약 내역")

    st.caption(
        "내가 예약한 좌석과 이용 시간을 확인할 수 있습니다."
    )

    my_reservations = get_my_reservations(
        st.session_state.user["id"]
    )

    if not my_reservations:

        st.info("현재 예약 내역이 없습니다.")

    else:

        st.write(
            f"총 **{len(my_reservations)}건**의 예약이 있습니다."
        )

        for reservation in my_reservations:

            rid, room, seat, start, end = reservation

            now_string = format_datetime(get_now())

            is_active = (
                start <= now_string < end
            )

            with st.container(border=True):

                c1, c2 = st.columns([3, 1])

                with c1:

                    st.markdown(
                        f"### 🏫 {room} / {seat}"
                    )

                    st.write(f"📅 시작: {start}")
                    st.write(f"⏰ 종료: {end}")

                    if is_active:

                        st.success("이용 중")

                    elif end <= now_string:

                        st.caption("이용 종료")

                    else:

                        st.info("이용 예정")

                with c2:

                    if end > now_string:

                        if st.button(
                            "예약 취소",
                            key=f"cancel_{rid}",
                            use_container_width=True
                        ):

                            result = cancel_reservation(
                                rid,
                                st.session_state.user["id"]
                            )

                            if result:

                                st.success(
                                    "예약이 취소되었습니다."
                                )

                                st.rerun()

                            else:

                                st.error(
                                    "예약 취소에 실패했습니다."
                                )


# ==========================================
# 14. 전체 예약 현황
# ==========================================

with tab3:

    st.header("📊 전체 자습실 현황")

    st.caption(
        "현재 시각부터 선택한 시간 동안 이용 가능한 좌석을 확인합니다."
    )

    dashboard_duration_label = st.selectbox(
        "조회할 이용 시간",
        list(DURATION_OPTIONS.keys()),
        key="dashboard_duration"
    )

    dashboard_duration = DURATION_OPTIONS[
        dashboard_duration_label
    ]

    dashboard_start, dashboard_end = get_current_period(
        dashboard_duration
    )

    st.info(
        f"조회 시간: {dashboard_start.strftime('%H:%M')} ~ "
        f"{dashboard_end.strftime('%H:%M')}"
    )

    if not check_operating_hours(
        dashboard_start,
        dashboard_end
    ):

        st.warning(
            "선택한 조회 시간은 오후 10시 운영 종료 시간을 초과합니다."
        )

    # 전체 예약 통계

    total_booked = 0

    for room in ROOMS:

        total_booked += len(
            get_booked_seats(
                dashboard_start,
                dashboard_end,
                room
            )
        )

    total_available = TOTAL_SEATS - total_booked

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "전체 좌석",
        f"{TOTAL_SEATS}석"
    )

    c2.metric(
        "예약 완료",
        f"{total_booked}석"
    )

    c3.metric(
        "예약 가능",
        f"{total_available}석"
    )

    st.progress(
        total_booked / TOTAL_SEATS
    )

    st.caption(
        f"예약률: {total_booked / TOTAL_SEATS * 100:.1f}%"
    )

    st.divider()

    # 자습실별 현황

    st.markdown("### 🏫 자습실별 좌석 현황")

    for room, seats in ROOMS.items():

        booked = get_booked_seats(
            dashboard_start,
            dashboard_end,
            room
        )

        available = len(seats) - len(booked)

        with st.expander(
            f"{room} | 예약 {len(booked)}석 / 잔여 {available}석",
            expanded=True
        ):

            st.write("🔴 예약 완료 좌석")

            st.write(
                ", ".join(sorted(booked))
                if booked
                else "예약된 좌석이 없습니다."
            )

            st.write("🟢 예약 가능 좌석")

            st.write(
                ", ".join(
                    seat for seat in seats
                    if seat not in booked
                )
                if available
                else "잔여 좌석이 없습니다."
            )


# ==========================================
# 15. 관리자 상세 조회
# ==========================================

    st.divider()

    st.subheader("🔐 관리자 상세 조회")

    st.caption(
        "관리자 비밀번호를 입력하면 전체 예약자 정보를 확인할 수 있습니다."
    )

    admin_password = st.text_input(
        "관리자 비밀번호",
        type="password",
        key="admin_password"
    )

    if st.button(
        "관리자 예약 데이터 확인",
        use_container_width=True
    ):

        if admin_password == ADMIN_PASSWORD:

            with get_connection() as conn:

                records = conn.execute("""
                    SELECT
                        student_name,
                        student_id,
                        room,
                        seat,
                        start_time,
                        end_time,
                        created_at

                    FROM reservations

                    ORDER BY start_time DESC

                """).fetchall()

            if records:

                st.success(
                    f"총 {len(records)}건의 예약 데이터를 확인했습니다."
                )

                st.dataframe(
                    [
                        {
                            "이름": row[0],
                            "학번": row[1],
                            "자습실": row[2],
                            "좌석": row[3],
                            "예약 시작": row[4],
                            "예약 종료": row[5],
                            "예약 생성": row[6]
                        }
                        for row in records
                    ],
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info("아직 예약 내역이 없습니다.")

        else:

            st.error(
                "관리자 비밀번호가 올바르지 않습니다."
            )


# ==========================================
# 16. 하단 정보
# ==========================================

st.divider()

st.markdown(
    """
    <div style="
        text-align:center;
        color:#94A3B8;
        font-size:12px;
        padding:20px;
    ">
        <b>STUDY HUB</b><br>
        SMART STUDY ROOM RESERVATION SYSTEM<br><br>

        3F A ROOM · 3F B ROOM · 4F C ROOM<br>

        TOTAL 120 SEATS<br><br>

        OPERATING HOURS : UNTIL 22:00
    </div>
    """,
    unsafe_allow_html=True
)
