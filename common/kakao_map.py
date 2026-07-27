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

# 카테고리별 마커 아이콘 (category_icons 인자에 넣어서 쓴다).
# 인라인 SVG라 외부 이미지 요청이 없고, 흰색으로 그려져 마커 배경색 위에 얹힌다.
ICON_PARKING = (
    '<svg viewBox="0 0 24 24" width="16" height="16">'
    '<text x="12" y="18" text-anchor="middle" font-size="17" font-weight="700"'
    ' fill="currentColor" font-family="Pretendard, sans-serif">P</text>'
    "</svg>"
)

ICON_MY_LOCATION = (
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none"'
    ' stroke="currentColor" stroke-width="2.4" stroke-linecap="round">'
    '<circle cx="12" cy="12" r="4.5" fill="currentColor" stroke="none"/>'
    '<path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3"/>'
    "</svg>"
)

ICON_CCTV = (
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">'
    '<rect x="1.5" y="7" width="13" height="6.5" rx="1.5"/>'
    '<path d="M15 8.6l5.5-2.6v11l-5.5-2.6z"/>'
    '<path d="M6 13.5h2.6v5a1.3 1.3 0 0 1-2.6 0z"/>'
    "</svg>"
)


def _details(value) -> list[list[str]]:
    """말풍선에 표 형태로 넣을 [라벨, 값] 목록. 없으면 빈 목록."""
    if not isinstance(value, (list, tuple)):
        return []
    return [[str(pair[0]), str(pair[1])] for pair in value if len(pair) >= 2]


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
    polygons: list[dict] | None = None,
    category_icons: dict[str, str] | None = None,
) -> str:
    """마커(+선택적 폴리곤)가 찍힌 카카오맵 HTML을 문자열로 반환.

    df는 최소한 name, lat, lng, category, info 컬럼을 가지고 있어야 한다.
    좌표가 비어 있는 행은 마커를 찍을 수 없으므로 조용히 건너뛴다.

    polygons는 구역을 색으로 칠할 때 쓴다 (단속 다발구역 등). 각 항목은
        {"path": [[위도, 경도], ...], "color": "#e63946", "opacity": 0.35,
         "name": "표시명", "info": "말풍선 내용"}
    형태이고, 넘기지 않으면 기존 호출부(CCTV 지도 등)와 동작이 완전히 같다.

    category_icons는 특정 카테고리의 마커를 원형 점 대신 아이콘으로 그린다.
    예) category_icons={"단속 CCTV": ICON_CCTV}
    값은 신뢰할 수 있는 마크업만 넣어야 한다 (innerHTML로 삽입된다).
    """
    category_colors = category_colors or {}
    category_icons = category_icons or {}
    polygons_json = json.dumps(polygons or [], ensure_ascii=False)

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
                "icon": category_icons.get(row.get("category", ""), ""),
                "details": _details(row.get("details")),
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

            /* 아이콘 마커 (CCTV 등) */
            .pin.icon {{
                width: 24px; height: 24px;
                border-radius: 7px;
                display: flex; align-items: center; justify-content: center;
                color: #ffffff;
            }}
            .pin.icon svg {{ display: block; }}

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
                min-width: 200px;
                max-width: 280px;
                white-space: normal;
            }}
            .bubble .title {{
                font-weight: 700; font-size: 13.5px; color:#1f2544;
                margin-bottom: 4px; word-break: keep-all;
            }}
            .bubble .cat {{
                display:inline-block; font-size:10.5px; font-weight:600; color:#fff;
                border-radius:999px; padding:1px 8px;
            }}
            .bubble .info {{
                display:block; color:#6b7280; font-size:11.5px;
                margin-top:5px; word-break: keep-all;
            }}
            .bubble .rows {{
                margin-top:8px; padding-top:7px; border-top:1px solid #eef0f5;
                display:flex; flex-direction:column; gap:4px;
            }}
            .bubble .row {{ display:flex; gap:10px; align-items:baseline; }}
            .bubble .row .k {{
                flex:0 0 46px; color:#9095a3; font-size:11px;
            }}
            .bubble .row .v {{
                flex:1; color:#2b2f3a; font-weight:600; word-break: keep-all;
            }}
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
            var polygons = {polygons_json};
            var openBubble = null;

            // 구역 색칠 (단속 다발구역 등). 마커보다 먼저 그려 마커가 위에 오게 한다.
            polygons.forEach(function(p) {{
                var path = p.path.map(function(pt) {{
                    return new kakao.maps.LatLng(pt[0], pt[1]);
                }});
                var area = new kakao.maps.Polygon({{
                    path: path,
                    strokeWeight: 1,
                    strokeColor: p.color,
                    strokeOpacity: 0.7,
                    strokeStyle: 'solid',
                    fillColor: p.color,
                    fillOpacity: p.opacity
                }});
                area.setMap(map);

                // 마우스를 올리면 진해져서 어느 칸인지 알아보기 쉽다
                kakao.maps.event.addListener(area, 'mouseover', function() {{
                    area.setOptions({{ fillOpacity: Math.min(p.opacity + 0.25, 0.9) }});
                }});
                kakao.maps.event.addListener(area, 'mouseout', function() {{
                    area.setOptions({{ fillOpacity: p.opacity }});
                }});

                kakao.maps.event.addListener(area, 'click', function(mouseEvent) {{
                    if (openBubble) openBubble.setMap(null);
                    var html = '<div class="bubble">'
                        + '<div class="title">' + p.name + '</div>'
                        + '<span class="cat" style="background:' + p.color + '">구역</span><br/>'
                        + '<span class="info">' + p.info + '</span>'
                        + '</div>';
                    openBubble = new kakao.maps.CustomOverlay({{
                        position: mouseEvent.latLng, content: html, yAnchor: 1.35, zIndex: 20
                    }});
                    openBubble.setMap(map);
                }});
            }});

            function drawMarker(m, pos) {{
                // 원형 커스텀 마커
                var pinEl = document.createElement('div');
                pinEl.className = m.icon ? 'pin icon' : 'pin';
                pinEl.style.background = m.color;
                if (m.icon) pinEl.innerHTML = m.icon;
                new kakao.maps.CustomOverlay({{
                    position: pos, content: pinEl, map: map, yAnchor: 0.5
                }});

                // 클릭 시 말풍선 (하나만 열리도록 토글)
                var rows = (m.details || []).map(function(d) {{
                    return '<div class="row"><span class="k">' + d[0] + '</span>'
                         + '<span class="v">' + d[1] + '</span></div>';
                }}).join('');
                var bubbleHtml = '<div class="bubble">'
                    + '<div class="title">' + m.name + '</div>'
                    + (m.category ? '<span class="cat" style="background:' + m.color + '">' + m.category + '</span>' : '')
                    + (m.info ? '<span class="info">' + m.info + '</span>' : '')
                    + (rows ? '<div class="rows">' + rows + '</div>' : '')
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