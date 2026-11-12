
import streamlit as st
import sqlite3
import os
from datetime import date, datetime

# ==========================================
# 1. 기본 설정
# ==========================================

st.set_page_config(
    page_title="STUDY HUB",
    page_icon="📚",
    layout="wide"
)

DB_PATH = os.environ.get("STUDY_HUB_DB", "/tmp/study_hub.db")

ROOMS = {
    "3층 A실": [f"A{i:02d}" for i in range(1, 31)],
    "3층 B실": [f"B{i:02d}" for i in range(1, 31)],
    "4층 C실": [f"C{i:02d}" for i in range(1, 61)]
}

TIME_SLOTS = [
    "16:00 ~ 17:00",
    "17:00 ~ 18:00",
    "18:00 ~ 19:00",
    "19:00 ~ 20:00",
    "20:00 ~ 21:00",
    "21:00 ~ 22:00"
]

# ==========================================
# 2. 화면 디자인
# ==========================================

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
    }

    .stApp {
        background-color: #F5F7FB;
    }

    .main-title {
        font-size: 36px;
        font-weight: 800;
        color: #172554;
        letter-spacing: -1px;
    }

    .sub-title {
        color: #64748B;
        font-size: 15px;
    }

    section[data-testid="stSidebar"] {
        background-color: #172554;
    }

    section[data-testid="stSidebar"] * {
        color: white;
    }

    div.stButton > button {
        border-radius: 9px;
        font-weight: 600;
        min-height: 42px;
    }

    h1, h2, h3 {
        color: #172554;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 데이터베이스 연결
# ==========================================

def get_connection():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=15,
        check_same_thread=False
    )
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def init_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                reservation_date TEXT NOT NULL,
                time_slot TEXT NOT NULL,
                room TEXT NOT NULL,
                seat TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(reservation_date, time_slot, room, seat),
                UNIQUE(reservation_date, time_slot, student_id)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reservation_search
            ON reservations(reservation_date, time_slot, room)
        """)


init_database()

# ==========================================
# 4. 예약 데이터 조회
# ==========================================

def get_booked_seats(res_date, time_slot, room):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT seat
            FROM reservations
            WHERE reservation_date = ?
            AND time_slot = ?
            AND room = ?
        """, (res_date, time_slot, room)).fetchall()

    return {row[0] for row in rows}


def get_reservation_count(res_date, time_slot):
    with get_connection() as conn:
        result = conn.execute("""
            SELECT COUNT(*)
            FROM reservations
            WHERE reservation_date = ?
            AND time_slot = ?
        """, (res_date, time_slot)).fetchone()

    return result[0]


def get_my_reservations(student_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, reservation_date, time_slot, room, seat
            FROM reservations
            WHERE student_id = ?
            ORDER BY reservation_date, time_slot
        """, (student_id,)).fetchall()

    return rows

# ==========================================
# 5. 좌석 예약 처리
# ==========================================

def make_reservation(
    student_id,
    student_name,
    res_date,
    time_slot,
    room,
    seat
):
    if room not in ROOMS or seat not in ROOMS[room]:
        return False, "올바르지 않은 좌석입니다."

    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")

        existing_user = conn.execute("""
            SELECT id FROM reservations
            WHERE student_id = ?
            AND reservation_date = ?
            AND time_slot = ?
        """, (student_id, res_date, time_slot)).fetchone()

        if existing_user:
            conn.rollback()
            return False, "해당 시간에 이미 예약한 좌석이 있습니다."

        existing_seat = conn.execute("""
            SELECT id FROM reservations
            WHERE reservation_date = ?
            AND time_slot = ?
            AND room = ?
            AND seat = ?
        """, (res_date, time_slot, room, seat)).fetchone()

        if existing_seat:
            conn.rollback()
            return False, "이미 예약된 좌석입니다."

        conn.execute("""
            INSERT INTO reservations (
                student_id,
                student_name,
                reservation_date,
                time_slot,
                room,
                seat,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            student_id,
            student_name,
            res_date,
            time_slot,
            room,
            seat,
            datetime.now().isoformat(timespec="seconds")
        ))

        conn.commit()
        return True, "예약이 완료되었습니다!"

    except sqlite3.IntegrityError:
        conn.rollback()
        return False, "중복 예약입니다. 좌석을 다시 확인해 주세요."

    except sqlite3.Error:
        conn.rollback()
        return False, "데이터베이스 오류가 발생했습니다."

    finally:
        conn.close()

# ==========================================
# 6. 예약 취소
# ==========================================

def cancel_reservation(reservation_id, student_id):
    with get_connection() as conn:
        result = conn.execute("""
            DELETE FROM reservations
            WHERE id = ? AND student_id = ?
        """, (reservation_id, student_id))

    return result.rowcount > 0

# ==========================================
# 7. 사용자 로그인
# ==========================================

if "user" not in st.session_state:
    st.session_state.user = None

if "selected_seat" not in st.session_state:
    st.session_state.selected_seat = None

if "selection_key" not in st.session_state:
    st.session_state.selection_key = None


with st.sidebar:

    st.markdown("# 📚 STUDY HUB")
    st.caption("SMART STUDY ROOM RESERVATION")
    st.divider()

    if st.session_state.user is None:

        st.markdown("### 사용자 로그인")
        st.caption("이름과 학번을 입력해 주세요.")

        with st.form("login_form"):

            student_name = st.text_input(
                "이름",
                placeholder="이름 입력",
                max_chars=20
            )

            student_id = st.text_input(
                "학번",
                placeholder="학번 입력",
                max_chars=20
            )

            login_button = st.form_submit_button(
                "로그인",
                use_container_width=True
            )

            if login_button:

                student_name = student_name.strip()
                student_id = student_id.strip()

                if not student_name or not student_id:
                    st.error("이름과 학번을 입력해 주세요.")

                elif len(student_id) < 2:
                    st.error("학번을 올바르게 입력해 주세요.")

                else:
                    st.session_state.user = {
                        "name": student_name,
                        "id": student_id
                    }

                    st.session_state.selected_seat = None

                    st.rerun()

    else:

        st.success(
            f"{st.session_state.user['name']}님 환영합니다!"
        )

        st.caption(
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


# ==========================================
# 8. 메인 화면
# ==========================================

st.markdown(
    '<div class="main-title">STUDY HUB</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-title">스마트 자습실 좌석 예약 시스템</div>',
    unsafe_allow_html=True
)

st.write("")


# 로그인하지 않은 사용자 화면

if st.session_state.user is None:

    st.info(
        "왼쪽 메뉴에서 이름과 학번을 입력하고 로그인해 주세요."
    )

    st.markdown("## 📚 편리한 자습실 예약")

    st.write(
        "원하는 날짜와 시간, 자습실을 선택하고 "
        "실시간 잔여 좌석을 확인할 수 있습니다."
    )

    col1, col2, col3 = st.columns(3)

    col1.metric("전체 좌석", "120석")
    col2.metric("자습실", "3개")
    col3.metric("예약 단위", "1시간")

    st.stop()


# ==========================================
# 9. 메뉴 구성
# ==========================================

tab1, tab2, tab3 = st.tabs([
    "🪑 좌석 예약",
    "📋 내 예약",
    "📊 전체 현황"
])


# ==========================================
# 10. 좌석 예약 화면
# ==========================================

with tab1:

    st.header("🪑 좌석 예약")

    st.caption(
        "원하는 날짜와 시간, 자습실을 선택해 주세요."
    )

    col1, col2 = st.columns(2)

    with col1:

        selected_date = st.date_input(
            "📅 예약 날짜",
            value=date.today(),
            min_value=date.today()
        )

    with col2:

        selected_time = st.selectbox(
            "🕒 이용 시간",
            TIME_SLOTS
        )

    selected_room = st.selectbox(
        "🏫 자습실 선택",
        list(ROOMS.keys())
    )

    date_string = selected_date.isoformat()

    # 예약된 좌석 조회

    booked_seats = get_booked_seats(
        date_string,
        selected_time,
        selected_room
    )

    all_seats = ROOMS[selected_room]

    available_count = (
        len(all_seats) - len(booked_seats)
    )

    st.divider()

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

    st.write("")

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
        "🟢 예약 가능   🔴 예약 완료   🔵 선택한 좌석"
    )

    # 날짜, 시간, 자습실이 바뀌면 선택 초기화

    selected_key = (
        date_string,
        selected_time,
        selected_room
    )

    if st.session_state.selection_key != selected_key:

        st.session_state.selected_seat = None
        st.session_state.selection_key = selected_key

    # 좌석 버튼 생성

    columns = st.columns(5)

    for index, seat in enumerate(all_seats):

        with columns[index % 5]:

            is_booked = seat in booked_seats

            is_selected = (
                st.session_state.selected_seat == seat
            )

            if is_booked:

                button_type = "secondary"
                disabled = True
                label = f"🔴 {seat}"

            elif is_selected:

                button_type = "primary"
                disabled = False
                label = f"🔵 {seat}"

            else:

                button_type = "secondary"
                disabled = False
                label = f"🟢 {seat}"

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

    # 예약 확인

    st.markdown("### 예약 정보 확인")

    if st.session_state.selected_seat:

        st.info(
            f"""
            **선택한 자습실:** {selected_room}

            **선택한 좌석:** {st.session_state.selected_seat}

            **예약 날짜:** {date_string}

            **이용 시간:** {selected_time}

            **예약자:** {st.session_state.user['name']}
            """
        )

        if st.button(
            "✅ 예약 확정하기",
            type="primary",
            use_container_width=True
        ):

            success, message = make_reservation(
                st.session_state.user["id"],
                st.session_state.user["name"],
                date_string,
                selected_time,
                selected_room,
                st.session_state.selected_seat
            )

            if success:

                st.session_state.selected_seat = None

                st.success(message)

                st.rerun()

            else:

                st.error(message)

    else:

        st.warning(
            "예약할 좌석을 먼저 선택해 주세요."
        )

# ==========================================
# 11. 내 예약 내역
# ==========================================

with tab2:

    st.header("📋 내 예약 내역")

    st.caption(
        "내가 예약한 자습실과 좌석을 확인할 수 있습니다."
    )

    my_reservations = get_my_reservations(
        st.session_state.user["id"]
    )

    if not my_reservations:

        st.info("현재 예약된 좌석이 없습니다.")

    else:

        st.write(
            f"총 **{len(my_reservations)}건**의 예약이 있습니다."
        )

        for reservation in my_reservations:

            rid, res_date, time_slot, room, seat = reservation

            with st.container(border=True):

                c1, c2 = st.columns([3, 1])

                with c1:

                    st.markdown(
                        f"**🏫 {room} / {seat}**"
                    )

                    st.write(f"📅 예약 날짜: {res_date}")

                    st.write(f"🕒 이용 시간: {time_slot}")

                with c2:

                    if st.button(
                        "예약 취소",
                        key=f"cancel_{rid}",
                        use_container_width=True
                    ):

                        if cancel_reservation(
                            rid,
                            st.session_state.user["id"]
                        ):

                            st.success(
                                "예약이 취소되었습니다."
                            )

                            st.rerun()

                        else:

                            st.error(
                                "예약 취소에 실패했습니다."
                            )


# ==========================================
# 12. 전체 예약 현황
# ==========================================

with tab3:

    st.header("📊 전체 예약 현황")

    st.caption(
        "날짜와 시간대별 자습실 예약 현황을 확인합니다."
    )

    dashboard_date = st.date_input(
        "현황 조회 날짜",
        value=date.today(),
        min_value=date.today(),
        key="dashboard_date"
    )

    dashboard_time = st.selectbox(
        "현황 조회 시간",
        TIME_SLOTS,
        key="dashboard_time"
    )

    dashboard_date_string = dashboard_date.isoformat()

    # 전체 예약 통계

    total_seats = 120

    total_booked = get_reservation_count(
        dashboard_date_string,
        dashboard_time
    )

    total_available = (
        total_seats - total_booked
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "전체 좌석",
        f"{total_seats}석"
    )

    c2.metric(
        "예약 완료",
        f"{total_booked}석"
    )

    c3.metric(
        "잔여 좌석",
        f"{total_available}석"
    )

    # 예약률

    reservation_rate = total_booked / total_seats

    st.progress(reservation_rate)

    st.caption(
        f"전체 예약률: {reservation_rate * 100:.1f}%"
    )

    st.divider()

    # 자습실별 예약 현황

    st.markdown("### 🏫 자습실별 현황")

    for room, seats in ROOMS.items():

        booked = get_booked_seats(
            dashboard_date_string,
            dashboard_time,
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

    # ======================================
    # 13. 관리자 상세 조회
    # ======================================

    st.divider()

    st.subheader("🔐 관리자 상세 조회")

    st.caption(
        "관리자 비밀번호를 입력하면 해당 시간대의 예약자 정보를 확인할 수 있습니다."
    )

    admin_password = st.text_input(
        "관리자 비밀번호",
        type="password",
        key="admin_password"
    )

    if st.button(
        "관리자 데이터 확인",
        use_container_width=True
    ):

        correct_password = os.environ.get(
            "STUDY_HUB_ADMIN_PASSWORD",
            "studyhub1234"
        )

        if admin_password == correct_password:

            with get_connection() as conn:

                records = conn.execute("""
                    SELECT
                        student_name,
                        student_id,
                        reservation_date,
                        time_slot,
                        room,
                        seat
                    FROM reservations
                    WHERE reservation_date = ?
                    AND time_slot = ?
                    ORDER BY room, seat
                """, (
                    dashboard_date_string,
                    dashboard_time
                )).fetchall()

            if records:

                st.success(
                    f"총 {len(records)}건의 예약 내역을 확인했습니다."
                )

                st.dataframe(
                    [
                        {
                            "이름": row[0],
                            "학번": row[1],
                            "날짜": row[2],
                            "시간": row[3],
                            "자습실": row[4],
                            "좌석": row[5]
                        }
                        for row in records
                    ],
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "해당 시간대에 예약 내역이 없습니다."
                )

        else:

            st.error(
                "관리자 비밀번호가 올바르지 않습니다."
            )


# ==========================================
# 14. 하단 정보
# ==========================================

st.divider()

st.markdown(
    """
    <div style="
        text-align:center;
        color:#94A3B8;
        font-size:12px;
        padding:15px;
    ">
        <b>STUDY HUB</b><br>
        SMART STUDY ROOM RESERVATION SYSTEM<br><br>
        3F A ROOM · 3F B ROOM · 4F C ROOM<br>
        TOTAL 120 SEATS<br><br>
        © STUDY HUB
    </div>
    """,
    unsafe_allow_html=True
)
