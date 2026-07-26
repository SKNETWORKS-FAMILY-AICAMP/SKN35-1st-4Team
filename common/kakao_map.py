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

def _coord(value) -> float | None:
    """좌표를 float로. 결측/변환불가면 None (마커를 찍지 않는다)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


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
    좌표가 비어 있는 행은 마커를 찍을 수 없으므로 조용히 건너뛴다.
    """
    category_colors = category_colors or {}

    # 마커 데이터를 JSON으로 한 번에 넘긴다 (행별 f-string 이스케이프 문제 방지)
    markers = []
    for _, row in df.iterrows():
        lat, lng = _coord(row["lat"]), _coord(row["lng"])
        if lat is None or lng is None:
            continue
        markers.append(
            {
                "name": str(row["name"]),
                "lat": lat,
                "lng": lng,
                "category": str(row.get("category", "")),
                "info": str(row.get("info", "")),
                "color": category_colors.get(row.get("category", ""), DEFAULT_COLOR),
            }
        )
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

            /* SDK 로드 실패 안내 */
            .sdk-error {{
                display:flex; flex-direction:column; justify-content:center;
                height:100%; box-sizing:border-box;
                background:#fff7f7; border:1px solid #f5b5b5; border-radius:14px;
                padding:24px 28px; color:#b91c1c;
                font-family:'Pretendard', -apple-system, 'Malgun Gothic', sans-serif;
                font-size:13.5px; line-height:1.7;
            }}
            .sdk-error code {{
                background:#fdeaea; padding:1px 6px; border-radius:5px; font-size:12.5px;
            }}
            .sdk-error .hint {{ display:block; margin-top:10px; color:#7a5252; font-size:12.5px; }}
        </style>
    </head>
    <body>
        <div style="position:relative;">
            {legend_html}
            <div id="map"></div>
        </div>
        <script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={app_key}"></script>
        <script>
            // SDK가 안 붙으면(키 오류/도메인 미등록) 지도가 그냥 빈 화면이 되어 원인을 알 수 없다.
            // 가장 흔한 원인은 "지금 접속 중인 주소:포트"가 카카오 콘솔에 등록되지 않은 경우다.
            if (!window.kakao || !window.kakao.maps) {{
                document.getElementById('map').innerHTML =
                    '<div class="sdk-error">'
                    + '<b>카카오맵 SDK를 불러오지 못했습니다.</b><br/>'
                    + '카카오 개발자 콘솔 &gt; 내 애플리케이션 &gt; 앱 설정 &gt; 플랫폼 &gt; Web 에<br/>'
                    + '<code>' + (window.parent !== window ? document.referrer || '현재 주소' : location.origin) + '</code>'
                    + ' 를 사이트 도메인으로 등록했는지 확인하세요.<br/>'
                    + '<span class="hint">포트가 다르면 다른 도메인으로 취급됩니다 '
                    + '(localhost:8501 등록 → localhost:8502는 차단).<br/>'
                    + '.env 의 KAKAO_JS_KEY 가 JavaScript 키인지도 확인하세요 (REST 키 아님).</span>'
                    + '</div>';
                throw new Error('Kakao Maps SDK not loaded');
            }}

            var map = new kakao.maps.Map(document.getElementById('map'), {{
                center: new kakao.maps.LatLng({center_lat}, {center_lng}),
                level: {level}
            }});
            map.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT);

            var markers = {markers_json};
            var openBubble = null;

            function drawMarker(m, pos) {{
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
            }}

            markers.forEach(function(m) {{
                drawMarker(m, new kakao.maps.LatLng(m.lat, m.lng));
            }});

            // 지도 빈 곳 클릭 시 말풍선 닫기
            kakao.maps.event.addListener(map, 'click', function() {{
                if (openBubble) {{ openBubble.setMap(null); openBubble = null; }}
            }});
        </script>
    </body>
    </html>
    """