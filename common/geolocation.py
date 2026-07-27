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

_CSS = """
.geo button {
  width: 100%; padding: 8px 12px; border-radius: 10px;
  border: 1px solid #4361ee; background: #fff; color: #4361ee;
  font-weight: 600; cursor: pointer;
}
.geo button:hover { background: #4361ee; color: #fff; }
.geo #status { margin-top: 6px; font-size: 12px; color: #6b7280; min-height: 16px; }
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