"""
[담당: 승희] 브라우저 현재 위치 가져오기 (st.components.v2 커스텀 컴포넌트).

Streamlit에는 위치 기능이 없어서 브라우저 Geolocation API를 직접 붙였다.
버튼을 누르면 브라우저가 권한을 묻고, 허용하면 좌표를 파이썬으로 넘긴다.

제약
    - HTTPS 또는 localhost 에서만 동작한다 (브라우저 보안 정책).
    - 실내·데스크톱은 오차가 수백 m까지 난다. 정확도(accuracy)를 같이 보여주고,
      사용자가 직접 좌표를 넣을 수 있는 대체 경로를 반드시 함께 제공한다.
"""

import streamlit as st

_HTML = """
<div class="geo">
  <button id="locate" type="button">현재 위치 가져오기</button>
  <div id="status"></div>
</div>
"""

# 색은 common/ui.py 의 브랜드 팔레트(BRAND #D14314)와 맞춘다.
# 컴포넌트는 iframe 안이라 앱 CSS가 닿지 않아 여기서 직접 지정해야 한다.
_CSS = """
.geo button {
  width: 100%; padding: 9px 12px; border-radius: 10px;
  border: 1px solid #D14314; background: #fff; color: #D14314;
  font-weight: 700; cursor: pointer;
  transition: background .15s ease, color .15s ease, box-shadow .15s ease;
}
.geo button:hover {
  background: #D14314; color: #fff;
  box-shadow: 0 4px 12px rgba(209, 67, 20, .25);
}
.geo #status { margin-top: 6px; font-size: 12px; color: #6B625C; min-height: 16px; }
"""

_JS = """
export default function (component) {
  const { parentElement, setTriggerValue } = component

  const button = parentElement.querySelector("#locate")
  const status = parentElement.querySelector("#status")
  if (!button) return

  button.onclick = () => {
    if (!navigator.geolocation) {
      status.textContent = "이 브라우저는 위치 기능을 지원하지 않습니다."
      return
    }
    status.textContent = "위치 확인 중…"

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        status.textContent = "위치를 가져왔습니다."
        setTriggerValue("position", {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        })
      },
      (err) => {
        status.textContent = "실패: " + err.message + " — 좌표 직접 입력을 사용하세요."
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    )
  }
}
"""

_geolocation = st.components.v2.component(
    "browser_geolocation", html=_HTML, css=_CSS, js=_JS
)

SESSION_KEY = "my_position"


def browser_position(key: str = "geolocation") -> dict | None:
    """위치 버튼을 그리고 마지막으로 받은 좌표를 돌려준다.

    setTriggerValue 로 넘어온 값은 한 번의 rerun 동안만 살아 있어서
    session_state 에 옮겨 담아야 이후 실행에서도 유지된다.
    """
    result = _geolocation(key=key, on_position_change=lambda: None)
    if result.position:
        st.session_state[SESSION_KEY] = result.position
    return st.session_state.get(SESSION_KEY)


def clear_position() -> None:
    st.session_state.pop(SESSION_KEY, None)


# ---------------------------------------------------------------------------
# 지도 마커 드래그 -> 파이썬
# ---------------------------------------------------------------------------
# 지도는 st.iframe 안에서 그려져서 파이썬과 직접 통신할 수 없다.
# 마커를 놓으면 iframe이 부모 창으로 postMessage 를 보내고(common/kakao_map.py),
# 여기 있는 보이지 않는 컴포넌트가 그 메시지를 받아 파이썬으로 넘긴다.
_BRIDGE_JS = """
export default function (component) {
  const { setTriggerValue } = component

  // 컴포넌트는 rerun마다 다시 실행되므로 이전 리스너를 먼저 걷어낸다
  if (window.__kakaoDragBridge) {
    window.removeEventListener("message", window.__kakaoDragBridge)
  }

  window.__kakaoDragBridge = (event) => {
    const data = event.data
    if (!data || data.type !== "kakao-map-drag") return
    if (typeof data.lat !== "number" || typeof data.lng !== "number") return
    setTriggerValue("dragged", { lat: data.lat, lng: data.lng })
  }

  window.addEventListener("message", window.__kakaoDragBridge)
}
"""

_drag_bridge = st.components.v2.component(
    "kakao_map_drag_bridge", html="", js=_BRIDGE_JS
)


def map_drag_position(key: str = "map_drag") -> dict | None:
    """지도에서 마커를 끌어 옮겼으면 그 좌표를 돌려준다 (없으면 None).

    화면에 아무것도 그리지 않는다. 사이드바 위젯보다 먼저 호출해야
    드래그 결과가 같은 실행에서 위도·경도 입력칸에도 반영된다.
    """
    result = _drag_bridge(key=key, on_dragged_change=lambda: None)
    if not result.dragged:
        return None

    position = {"lat": result.dragged["lat"], "lng": result.dragged["lng"], "accuracy": None}
    st.session_state[SESSION_KEY] = position
    return position