import os
import time
from datetime import datetime
import pandas as pd

from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

# 1. 브라우저 옵션 설정
options = Options()
options.add_argument("--start-maximized")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)
driver.get('https://jongno.eminwon.seoul.kr')
wait = WebDriverWait(driver, 10)

# 2. 메뉴 이동
menu = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "민원조회")))
menu.click()

public_menu = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "공개 상담민원 조회")))
public_menu.click()

print("크롤링을 시작합니다.")

search_types = ['제목', '내용']
keywords = ['주정차', '주차', '정차', '견인']

result_list = []
seen_ids = set()  # 고유 목록번호 저장용 Set

# 2016년 1월 1일 이후 게시글만 수집
CUTOFF_DATE = datetime.strptime("2016-01-01", "%Y-%m-%d")

# 3. 검색어별 순회
for search in search_types:
    for keyword in keywords:
        select_element = wait.until(EC.presence_of_element_located((By.ID, 'pt_field')))
        select = Select(select_element)
        select.select_by_visible_text(search)

        search_box = driver.find_element(By.ID, 'srhKeyword')
        search_box.clear()
        search_box.send_keys(keyword)

        driver.find_element(By.ID, 'searchBtn').click()

        try:
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "table.table tbody tr")))
        except:
            print(f'[{search}] - "{keyword}": 검색 결과가 없습니다.')
            continue

        page_num = 1
        stop_current_search = False

        # --- [페이지별 수집 루프] ---
        while True:
            time.sleep(1)
            table_rows = driver.find_elements(By.CSS_SELECTOR, "table.table tbody tr")
            print(f'\n[{search}] - "{keyword}" | {page_num}페이지 수집 중 (목록 {len(table_rows)}개)')

            # 3-1. 답변완료 항목 인덱스 추출
            target_indices = []
            for idx, row in enumerate(table_rows):
                try:
                    status = row.find_element(By.CSS_SELECTOR, "td.td-answer").text.strip()
                    if status == "답변완료":
                        target_indices.append(idx)
                except:
                    pass

            # 3-2. 항목별 수집
            for idx in target_indices:
                rows = driver.find_elements(By.CSS_SELECTOR, "table.table tbody tr")
                if idx >= len(rows):
                    break
                
                target_row = rows[idx]
                
                # 목록번호 및 작성일 사전 체크
                try:
                    tds = target_row.find_elements(By.TAG_NAME, "td")
                    post_num = tds[0].text.strip()
                    
                    list_date_str = ""
                    for td in tds:
                        txt = td.text.strip()
                        if len(txt) >= 10 and txt.count('-') == 2:
                            list_date_str = txt[:10]
                            break
                    
                    if list_date_str:
                        list_date_dt = datetime.strptime(list_date_str, "%Y-%m-%d")
                        if list_date_dt < CUTOFF_DATE:
                            print(f"  └ [날짜 제한 초과: {list_date_str}] 2016년 이전 게시물이 등장하여 해당 검색어 수집을 종료합니다.")
                            stop_current_search = True
                            break

                    if post_num and post_num in seen_ids:
                        print(f"  └ [중복 건너뜀 - 목록번호: {post_num}]")
                        continue
                except:
                    post_num = None

                if stop_current_search:
                    break

                title_link = target_row.find_element(By.CSS_SELECTOR, "td.td-list a")

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", title_link)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", title_link)

                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'td[colspan="6"]')))

                # --- [상세 페이지 데이터 추출] ---
                q_title, q_writer, q_date = "", "", ""
                a_depart, a_date = "", ""
                detail_post_num = ""

                ths = driver.find_elements(By.CSS_SELECTOR, '.bbs-table-view th')
                for th in ths:
                    th_text = th.text.strip()
                    try:
                        target_td = th.find_element(By.XPATH, 'following-sibling::td[1]').text.strip()
                        if '목록번호' in th_text: detail_post_num = target_td
                        elif '제목' in th_text: q_title = target_td
                        elif '작성자' in th_text: q_writer = target_td
                        elif '작성일' in th_text: q_date = target_td
                        elif '담당부서' in th_text: a_depart = target_td
                        elif '답변일자' in th_text: a_date = target_td
                    except:
                        pass

                q_date_clean = q_date[:10] if len(q_date) >= 10 else ""
                if q_date_clean:
                    try:
                        post_dt = datetime.strptime(q_date_clean, "%Y-%m-%d")
                        if post_dt < CUTOFF_DATE:
                            print(f"  └ [상세 날짜 제한: {q_date_clean}] 2016년 이전 게시물이므로 건너뜁니다.")
                            stop_current_search = True
                            driver.back()
                            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "table.table tbody tr")))
                            break
                    except:
                        pass

                final_post_num = detail_post_num if detail_post_num else post_num

                if final_post_num and final_post_num in seen_ids:
                    print(f"  └ [상세 중복 건너뜀 - 목록번호: {final_post_num}]")
                else:
                    if final_post_num:
                        seen_ids.add(final_post_num)

                    if not q_title:
                        try: q_title = driver.find_element(By.CSS_SELECTOR, '.bbs-table-view td[colspan="3"]').text.strip()
                        except: q_title = title_link.text.strip()

                    colspan_tds = driver.find_elements(By.CSS_SELECTOR, 'td[colspan="6"]')
                    
                    if len(colspan_tds) > 0:
                        raw_question = colspan_tds[0].text.strip()
                        question = raw_question.split('※ 첨부파일')[0].strip()
                    else:
                        question = ""

                    answer = colspan_tds[1].text.strip() if len(colspan_tds) > 1 else ""

                    # source 컬럼 제외 후 DB 구조에 맞게 매핑
                    data = {
                        'q_title': q_title[:100],
                        'q_writer': q_writer[:10],
                        'q_date': q_date,
                        'question': question,
                        'a_depart': a_depart[:50],
                        'a_date': a_date,
                        'answer': answer
                    }
                    result_list.append(data)
                    print(f"  (신규 수집 {len(result_list)}건 | 번호:{final_post_num}) 작성일: {q_date} | 제목: {q_title[:15]}...")

                driver.back()
                wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "table.table tbody tr")))

                if page_num > 1:
                    try:
                        curr_page_btn = driver.find_element(By.XPATH, f"//div[@id='navigator']//a[contains(text(), '{page_num}') or @title='{page_num}페이지']")
                        driver.execute_script("arguments[0].click();", curr_page_btn)
                        time.sleep(1)
                        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "table.table tbody tr")))
                    except:
                        pass

            if stop_current_search:
                break

            # 3-3. 다음 페이지 이동
            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, 'a[title="다음 페이지"]')
                href_attr = next_btn.get_attribute('href')

                if not href_attr or 'void(0)' in href_attr:
                    print(f"  └ [{search}] - '{keyword}': 마지막 페이지입니다.")
                    break

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", next_btn)

                page_num += 1
                time.sleep(1)
                wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "table.table tbody tr")))

            except Exception:
                print(f"  └ [{search}] - '{keyword}': 다음 페이지 버튼이 없어 종료합니다.")
                break

# 4. DataFrame 변환 및 최신순 정렬
df = pd.DataFrame(result_list)

df['q_date_dt'] = pd.to_datetime(df['q_date'], errors='coerce')
df.sort_values(by='q_date_dt', ascending=False, inplace=True)
df.drop(columns=['q_date_dt'], inplace=True)

df.insert(0, 'faq2_id', range(1, len(df) + 1))

# 5. CSV 저장
output_dir = os.path.join('data', 'cleaned')
os.makedirs(output_dir, exist_ok=True)

csv_filename = os.path.join(output_dir, 'complain_faq2_result.csv')
df.to_csv(csv_filename, index=False, encoding='utf-8-sig')

print(f"\n2016년 1월 1일 이후 데이터 크롤링이 완료되었습니다!")
print(f"최종 수집 건수: {len(df)}건 (source 컬럼 제외됨)")
print(f"저장 파일: {csv_filename}")

input("엔터를 누르면 종료합니다.")