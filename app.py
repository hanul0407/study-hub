
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import date
from pathlib import Path

# 1. 기본 설정
st.set_page_config(
    page_title="STUDY HUB",
    page_icon="📚",
    layout="wide"
)

DB_PATH = Path(__file__).parent / "study_hub.db"

st.markdown("""
<style>
.block-container {
    padding-top: 2rem;
    max-width: 1200px;
}
[data-testid="stSidebar"] {
    background-color: #F3F6FA;
}
div[data-testid="stMetric"] {
    background: #F5F8FC;
    padding: 18px;
    border-radius: 12px;
    border: 1px solid #E6ECF3;
}
div.stButton > button {
    border-radius: 9px;
    font-weight: 600;
    min-height: 42px;
}
</style>
""", unsafe_allow_html=True)


# 2. 데이터베이스 구축
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def initialize_database():
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS seats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            seat_number INTEGER NOT NULL,
            UNIQUE(room, seat_number)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            room TEXT NOT NULL,
            seat_number INTEGER NOT NULL,
            reservation_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '예약중',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS unique_active_seat
        ON reservations(reservation_date, room, seat_number)
        WHERE status = '예약중'
        """)

        conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS unique_active_student
        ON reservations(reservation_date, student_id)
        WHERE status = '예약중'
        """)

        for room in ["1자습실", "2자습실"]:
            for number in range(1, 13):
                conn.execute("""
                INSERT OR IGNORE INTO seats(room, seat_number)
                VALUES (?, ?)
                """, (room, number))


initialize_database()


# 3. 예약 관련 함수
def get_seats(room, selected_date):
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT
                s.seat_number,
                CASE
                    WHEN r.id IS NULL THEN '예약 가능'
                    ELSE '예약 완료'
                END AS status,
                r.student_id
            FROM seats s
            LEFT JOIN reservations r
                ON s.room = r.room
                AND s.seat_number = r.seat_number
                AND r.reservation_date = ?
                AND r.status = '예약중'
            WHERE s.room = ?
            ORDER BY s.seat_number
        """, conn, params=(selected_date, room))


def make_reservation(student_id, room, seat, selected_date):
    if not student_id.strip():
        return False, "학번 또는 별칭을 입력해 주세요."

    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO reservations(
                    student_id, room, seat_number, reservation_date
                )
                VALUES (?, ?, ?, ?)
            """, (student_id.strip(), room, seat, selected_date))

        return True, "좌석 예약이 완료되었습니다!"

    except sqlite3.IntegrityError:
        return False, "이미 예약된 좌석이거나 해당 날짜에 예약 내역이 있습니다."


def cancel_reservation(reservation_id, student_id):
    with get_connection() as conn:
        result = conn.execute("""
            UPDATE reservations
            SET status = '취소'
            WHERE id = ?
            AND student_id = ?
            AND status = '예약중'
        """, (reservation_id, student_id))

        return result.rowcount > 0


def get_my_reservations(student_id):
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT
                id AS 예약번호,
                reservation_date AS 이용날짜,
                room AS 자습실,
                seat_number AS 좌석번호,
                status AS 상태
            FROM reservations
            WHERE student_id = ?
            ORDER BY reservation_date DESC, id DESC
        """, conn, params=(student_id,))


def get_all_reservations():
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT
                id AS 예약번호,
                student_id AS 학생ID,
                reservation_date AS 이용날짜,
                room AS 자습실,
                seat_number AS 좌석번호,
                status AS 예약상태
            FROM reservations
            ORDER BY reservation_date DESC, id DESC
        """, conn)


# 4. 사이드바
with st.sidebar:
    st.markdown("# 📚 STUDY HUB")
    st.caption("SMART STUDY SPACE MANAGEMENT")

    st.divider()

    student_id = st.text_input(
        "학생 학번 또는 별칭",
        placeholder="예: 10101"
    ).strip()

    selected_date = st.date_input(
        "이용 날짜",
        value=date.today(),
        min_value=date.today()
    ).isoformat()

    st.divider()

    menu = st.radio(
        "SERVICE MENU",
        [
            "🏠 대시보드",
            "🪑 좌석 예약",
            "📋 나의 예약",
            "📊 이용 통계",
            "⚙️ 관리자 페이지"
        ]
    )

    st.divider()
    st.caption("STUDY HUB v1.0")
    st.caption("가상 학교 자습실 관리 시스템")


# 5. 공통 데이터
with get_connection() as conn:
    total_seats = pd.read_sql_query(
        "SELECT COUNT(*) AS total FROM seats",
        conn
    ).iloc[0]["total"]

    today_reserved = pd.read_sql_query("""
        SELECT COUNT(*) AS total
        FROM reservations
        WHERE reservation_date = ?
        AND status = '예약중'
    """, conn, params=(selected_date,)).iloc[0]["total"]

available_seats = total_seats - today_reserved
usage_rate = (
    today_reserved / total_seats * 100
    if total_seats else 0
)


# 6. 대시보드
if menu == "🏠 대시보드":
    st.title("📚 STUDY HUB")
    st.caption("스마트 자습실 예약 및 관리 시스템")

    st.info(f"📅 선택한 이용 날짜: {selected_date}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("전체 좌석", f"{total_seats}석")
    c2.metric("예약 완료", f"{today_reserved}석")
    c3.metric("예약 가능", f"{available_seats}석")
    c4.metric("이용률", f"{usage_rate:.1f}%")

    st.divider()
    st.subheader("자습실별 이용 현황")

    col1, col2 = st.columns(2)

    for col, room in zip(
        [col1, col2],
        ["1자습실", "2자습실"]
    ):
        with col:
            data = get_seats(room, selected_date)
            reserved = (data["status"] == "예약 완료").sum()
            available = len(data) - reserved

            st.markdown(f"### {room}")
            st.write(f"예약 {reserved}석 / 전체 {len(data)}석")
            st.progress(reserved / len(data))
            st.caption(f"예약 가능 {available}석")

    st.divider()
    st.subheader("전체 좌석 현황")

    for room in ["1자습실", "2자습실"]:
        data = get_seats(room, selected_date)
        st.markdown(f"**{room}**")

        cols = st.columns(6)

        for i, row in data.iterrows():
            with cols[i % 6]:
                if row["status"] == "예약 가능":
                    st.success(f"🟢 {row['seat_number']}번\n\n가능")
                else:
                    st.error(f"🔴 {row['seat_number']}번\n\n예약됨")


# 7. 좌석 예약
elif menu == "🪑 좌석 예약":
    st.title("🪑 좌석 예약")
    st.caption("원하는 자습실과 좌석을 선택해 주세요.")

    if not student_id:
        st.warning("먼저 사이드바에 학번 또는 별칭을 입력해 주세요.")

    else:
        room = st.selectbox(
            "자습실 선택",
            ["1자습실", "2자습실"]
        )

        st.write(f"### {room} 좌석 배치도")
        data = get_seats(room, selected_date)
        st.caption("🟢 예약 가능 | 🔴 예약 완료")

        for start in range(0, 12, 4):
            cols = st.columns(4)

            for i in range(start, min(start + 4, 12)):
                row = data.iloc[i]
                seat_num = int(row["seat_number"])

                with cols[i - start]:
                    if row["status"] == "예약 가능":
                        if st.button(
                            f"🟢 {seat_num}번 좌석",
                            key=f"seat_{room}_{seat_num}",
                            use_container_width=True
                        ):
                            st.session_state.selected_seat = seat_num
                            st.session_state.selected_room = room
                            st.session_state.selected_date = selected_date
                            st.session_state.selected_student = student_id

                    else:
                        st.button(
                            f"🔴 {seat_num}번 좌석",
                            key=f"occupied_{room}_{seat_num}",
                            disabled=True,
                            use_container_width=True
                        )

        if "selected_seat" in st.session_state:
            if (
                st.session_state.selected_room != room
                or st.session_state.selected_date != selected_date
                or st.session_state.selected_student != student_id
            ):
                del st.session_state.selected_seat
                st.rerun()

            seat = st.session_state.selected_seat

            st.divider()
            st.subheader("예약 정보 확인")
            st.write(f"학생: {student_id}")
            st.write(f"날짜: {selected_date}")
            st.write(f"자습실: {room}")
            st.write(f"좌석: {seat}번")

            if st.button(
                "예약 확정하기",
                type="primary",
                use_container_width=True
            ):
                success, message = make_reservation(
                    student_id, room, seat, selected_date
                )

                if success:
                    st.success(message)
                    del st.session_state.selected_seat
                    st.rerun()
                else:
                    st.error(message)

            if st.button("선택 취소"):
                del st.session_state.selected_seat
                st.rerun()


# 8. 나의 예약
elif menu == "📋 나의 예약":
    st.title("📋 나의 예약 내역")

    if not student_id:
        st.warning("학번 또는 별칭을 먼저 입력해 주세요.")

    else:
        data = get_my_reservations(student_id)

        if data.empty:
            st.info("예약 내역이 없습니다.")

        else:
            active = data[data["상태"] == "예약중"]

            st.metric("현재 예약 중인 좌석", f"{len(active)}개")

            st.dataframe(
                data,
                use_container_width=True,
                hide_index=True
            )

            st.divider()
            st.subheader("예약 취소")

            if not active.empty:
                reservation_id = st.selectbox(
                    "취소할 예약 선택",
                    active["예약번호"].tolist()
                )

                if st.button("예약 취소하기", type="primary"):
                    success = cancel_reservation(
                        int(reservation_id), student_id
                    )

                    if success:
                        st.success("예약이 취소되었습니다.")
                        st.rerun()
                    else:
                        st.error("예약 취소에 실패했습니다.")

            else:
                st.info("취소할 예약이 없습니다.")


# 9. 이용 통계
elif menu == "📊 이용 통계":
    st.title("📊 자습실 이용 통계")
    st.caption("예약 데이터를 바탕으로 자습실 이용 현황을 분석합니다.")

    all_data = get_all_reservations()
    active_data = all_data[
        all_data["예약상태"] == "예약중"
    ].copy()

    if active_data.empty:
        st.info("아직 분석할 예약 데이터가 없습니다.")

    else:
        room_stats = (
            active_data.groupby("자습실")
            .size()
            .reset_index(name="예약 수")
        )

        c1, c2 = st.columns(2)
        c1.metric("전체 예약 기록", f"{len(all_data)}건")
        c2.metric("현재 예약 건수", f"{len(active_data)}건")

        st.divider()
        st.subheader("자습실별 예약 현황")

        fig = px.bar(
            room_stats,
            x="자습실",
            y="예약 수",
            color="자습실",
            text="예약 수",
            color_discrete_sequence=["#3B82F6", "#14B8A6"]
        )

        fig.update_layout(
            showlegend=False,
            plot_bgcolor="white",
            paper_bgcolor="white"
        )

        st.plotly_chart(fig, use_container_width=True)

        st.subheader("날짜별 예약 추이")

        date_stats = (
            active_data.groupby("이용날짜")
            .size()
            .reset_index(name="예약 수")
            .sort_values("이용날짜")
        )

        fig2 = px.line(
            date_stats,
            x="이용날짜",
            y="예약 수",
            markers=True
        )

        st.plotly_chart(fig2, use_container_width=True)

        st.subheader("좌석 이용 현황")

        seat_stats = (
            active_data.groupby(["자습실", "좌석번호"])
            .size()
            .reset_index(name="예약 횟수")
        )

        st.dataframe(
            seat_stats.sort_values(
                "예약 횟수",
                ascending=False
            ),
            use_container_width=True,
            hide_index=True
        )


# 10. 관리자 페이지
elif menu == "⚙️ 관리자 페이지":
    st.title("⚙️ 관리자 대시보드")

    st.caption("전체 자습실 예약 데이터를 관리합니다.")

    st.warning(
        "교육용 시연 관리자 인증입니다. "
        "실제 서비스에는 안전한 인증 체계가 필요합니다."
    )

    admin_password = st.text_input(
        "관리자 비밀번호",
        type="password"
    )

    if admin_password == "studyhub-admin":
        st.success("관리자 인증 완료")

        admin_data = get_all_reservations()

        c1, c2, c3 = st.columns(3)

        c1.metric("전체 예약 기록", f"{len(admin_data)}건")
        c2.metric(
            "예약 중",
            f"{(admin_data['예약상태'] == '예약중').sum()}건"
        )
        c3.metric(
            "취소",
            f"{(admin_data['예약상태'] == '취소').sum()}건"
        )

        st.divider()
        st.subheader("전체 예약 기록")

        if admin_data.empty:
            st.info("등록된 예약이 없습니다.")

        else:
            st.dataframe(
                admin_data,
                use_container_width=True,
                hide_index=True
            )

            csv = admin_data.to_csv(
                index=False
            ).encode("utf-8-sig")

            st.download_button(
                "📥 예약 내역 CSV 다운로드",
                data=csv,
                file_name="study_hub_reservations.csv",
                mime="text/csv"
            )

    elif admin_password:
        st.error("비밀번호가 올바르지 않습니다.")


# 11. 푸터
st.divider()

st.caption(
    "STUDY HUB © 2026 | Smart Study Space Management System"
)

st.caption(
    "본 프로그램은 학교 자습실 운영을 가정한 교육용 시연 프로그램입니다."
)
