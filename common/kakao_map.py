"""
카카오맵 HTML 빌더 (공통 유틸).

모든 페이지(지도 조회, 주차장 검색 등)에서 이 함수 하나로 지도 HTML을 만들고
st.iframe(build_map_html(...), height=..., width="stretch") 형태로 사용하면 된다.

디자인:
- 기본 마커 대신 카테고리 색상의 원형 커스텀 마커(흰 테두리 + 그림자) 사용
- 클릭 시 둥근 모서리의 커스텀 말풍선(인포윈도우) 표시
- 좌측 상단에 카테고리 범례 자동 표시

사전 준비:
- 카카오 개발자 콘솔 > Web 플랫폼에 http://localhost:8501 등록
- .env의 KAKAO_JS_KEY에 JavaScript 키(REST 키 아님) 입력
"""

import json

import pandas as pd

DEFAULT_COLOR = "#4361ee"

def build_map_html(
    df: pd.DataFrame,
    app_key: str,
    center_lat: float,
    center_lng: float,
    category_colors: dict[str, str] | None = None,
    level: int = 6,
    height: int = 600,
) -> str:
    """마커가 찍힌 카카오맵 HTML을 문자열로 반환.

    df는 최소한 name, lat, lng, category, info 컬럼을 가지고 있어야 한다.
    """
    category_colors = category_colors or {}

    # 마커 데이터를 JSON으로 한 번에 넘긴다 (행별 f-string 이스케이프 문제 방지)
    markers = [
        {
            "name": str(row["name"]),
            "lat": float(row["lat"]),
            "lng": float(row["lng"]),
            "category": str(row.get("category", "")),
            "info": str(row.get("info", "")),
            "color": category_colors.get(row.get("category", ""), DEFAULT_COLOR),
        }
        for _, row in df.iterrows()
    ]
    markers_json = json.dumps(markers, ensure_ascii=False)

    # 범례 (카테고리 색상 매핑이 있을 때만)
    legend_items = "".join(
        f'<div class="legend-item"><span class="dot" style="background:{color}"></span>{cat}</div>'
        for cat, color in category_colors.items()
    )
    legend_html = f'<div id="legend">{legend_items}</div>' if legend_items else ""

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <meta name="referrer" content="unsafe-url" />
        <style>
            html, body {{ margin:0; padding:0; }}
            #map {{ width:100%; height:{height}px; border-radius:14px; }}

            /* 원형 커스텀 마커 */
            .pin {{
                width: 16px; height: 16px;
                border-radius: 50%;
                border: 3px solid #ffffff;
                box-shadow: 0 2px 6px rgba(0,0,0,.35);
                cursor: pointer;
                box-sizing: content-box;
            }}

            /* 말풍선 */
            .bubble {{
                position: relative;
                transform: translateY(-14px);
                background: #ffffff;
                border-radius: 12px;
                padding: 10px 14px;
                box-shadow: 0 6px 18px rgba(0,0,0,.18);
                font-family: 'Pretendard', -apple-system, 'Malgun Gothic', sans-serif;
                font-size: 12.5px;
                line-height: 1.5;
                max-width: 240px;
                white-space: normal;
            }}
            .bubble .title {{ font-weight: 700; margin-bottom: 2px; }}
            .bubble .cat {{
                display:inline-block; font-size:10.5px; font-weight:600; color:#fff;
                border-radius:999px; padding:1px 8px; margin-bottom:4px;
            }}
            .bubble .info {{ color:#555; }}
            .bubble::after {{
                content:""; position:absolute; left:50%; bottom:-7px;
                transform: translateX(-50%);
                border-left:7px solid transparent; border-right:7px solid transparent;
                border-top:7px solid #ffffff;
            }}

            /* 범례 */
            #legend {{
                position:absolute; top:12px; left:12px; z-index:10;
                background:rgba(255,255,255,.94);
                border-radius:10px; padding:8px 12px;
                box-shadow:0 2px 8px rgba(0,0,0,.15);
                font-family:'Pretendard', -apple-system, 'Malgun Gothic', sans-serif;
                font-size:12px;
            }}
            .legend-item {{ display:flex; align-items:center; gap:6px; padding:2px 0; }}
            .legend-item .dot {{
                width:10px; height:10px; border-radius:50%;
                border:2px solid #fff; box-shadow:0 1px 3px rgba(0,0,0,.3);
            }}
        </style>
    </head>
    <body>
        <div style="position:relative;">
            {legend_html}
            <div id="map"></div>
        </div>
        <script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={app_key}"></script>
        <script>
            var map = new kakao.maps.Map(document.getElementById('map'), {{
                center: new kakao.maps.LatLng({center_lat}, {center_lng}),
                level: {level}
            }});
            map.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT);

            var markers = {markers_json};
            var openBubble = null;

            markers.forEach(function(m) {{
                var pos = new kakao.maps.LatLng(m.lat, m.lng);

                // 원형 커스텀 마커
                var pinEl = document.createElement('div');
                pinEl.className = 'pin';
                pinEl.style.background = m.color;
                new kakao.maps.CustomOverlay({{
                    position: pos, content: pinEl, map: map, yAnchor: 0.5
                }});

                // 클릭 시 말풍선 (하나만 열리도록 토글)
                var bubbleHtml = '<div class="bubble">'
                    + '<div class="title">' + m.name + '</div>'
                    + (m.category ? '<span class="cat" style="background:' + m.color + '">' + m.category + '</span><br/>' : '')
                    + '<span class="info">' + m.info + '</span>'
                    + '</div>';
                var bubble = new kakao.maps.CustomOverlay({{
                    position: pos, content: bubbleHtml, yAnchor: 1.35, zIndex: 20
                }});

                pinEl.addEventListener('click', function() {{
                    if (openBubble) openBubble.setMap(null);
                    if (openBubble === bubble) {{ openBubble = null; return; }}
                    bubble.setMap(map);
                    openBubble = bubble;
                }});
            }});

            // 지도 빈 곳 클릭 시 말풍선 닫기
            kakao.maps.event.addListener(map, 'click', function() {{
                if (openBubble) {{ openBubble.setMap(null); openBubble = null; }}
            }});
        </script>
    </body>
    </html>
    """