import streamlit as st

def render():
    # Inject CSS + font calligraphy
    st.markdown(
        """
        <style>
          /* Tải vài font thư pháp, ưu tiên Dancing Script */
          @import url('https://fonts.googleapis.com/css2?family=Dancing+Script:wght@600;700&family=Great+Vibes&family=Satisfy&display=swap');

          .calligraphy-title{
            font-family: "Dancing Script","Great Vibes","Satisfy",cursive;
            font-size: 56px;
            line-height: 1.1;
            margin: .2em 0 .1em 0;
            letter-spacing: .5px;
            text-shadow: 0 2px 8px rgba(0,0,0,.06);
          }
          /* Thu nhỏ trên màn hình nhỏ */
          @media (max-width: 768px){
            .calligraphy-title{ font-size: 38px; }
          }
          /* Hỗ trợ dark theme: làm chữ sáng hơn chút */
          @media (prefers-color-scheme: dark){
            .calligraphy-title{ color: #f3f4f6; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Lời chào thư pháp
    st.markdown(
        '<div class="calligraphy-title">Xin chào các ! 👋</div>',
        unsafe_allow_html=True,
    )

    # Mô tả ngắn
    st.markdown(
        "Đây là trang quản lý các công cụ cần thiết cho IT."
    )

    st.info("Chọn mục ở thanh **sidebar** để bắt đầu.")
