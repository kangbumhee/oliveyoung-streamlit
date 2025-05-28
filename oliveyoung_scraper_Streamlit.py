import streamlit as st  # ✅ 가장 위에 있어야 함
st.set_page_config(  # ✅ Streamlit 관련 첫 번째 명령어여야 함
    page_title="올리브영 상품 크롤러",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)



import subprocess
import sys
import asyncio
import pandas as pd
import time
import re
from urllib.parse import quote
from datetime import datetime
import json
import os
import io
from PIL import Image
import requests
import webbrowser


# 라이브러리 설치 확인
try:
    from playwright.async_api import async_playwright
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.async_api import async_playwright

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    st.warning("📊 그래프 기능을 사용하려면 'pip install plotly' 를 설치해주세요")


)

class OliveYoungScraper:
    def __init__(self):
        self.base_url = "https://www.oliveyoung.co.kr/store/search/getSearchMain.do"
        self.products = []
        
    async def scrape_products(self, search_keywords, max_pages=1, progress_callback=None):
        """올리브영에서 여러 검색어로 상품 정보를 크롤링"""
        self.products = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                total_keywords = len(search_keywords)
                
                for keyword_idx, keyword in enumerate(search_keywords):
                    if progress_callback:
                        progress_callback(f"'{keyword}' 검색 중... ({keyword_idx + 1}/{total_keywords})")
                    
                    for page_num in range(1, max_pages + 1):
                        search_url = f"{self.base_url}?query={quote(keyword)}&giftYn=N&t_page=통합&t_click=검색창&t_search_name=검색&page={page_num}"
                        
                        await page.goto(search_url, wait_until="networkidle")
                        await asyncio.sleep(1)
                        
                        await self._scroll_to_load_all(page)
                        await self._extract_products(page, keyword, page_num)
                        
                        if progress_callback:
                            progress = (keyword_idx * max_pages + page_num) / (total_keywords * max_pages)
                            progress_callback(f"'{keyword}' {page_num}페이지 완료 - 총 {len(self.products)}개 상품", progress)
                        
            except Exception as e:
                if progress_callback:
                    progress_callback(f"오류 발생: {str(e)}", 1.0)
            finally:
                await browser.close()
                
        return self.products
    
    async def scrape_selected_products(self, selected_products, progress_callback=None):
        """선택된 상품들을 새로고침"""
        updated_products = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                total_products = len(selected_products)
                
                for idx, selected_product in enumerate(selected_products):
                    brand = selected_product.get('브랜드', '')
                    name = selected_product.get('상품명', '')[:20] + "..." if len(selected_product.get('상품명', '')) > 20 else selected_product.get('상품명', '')
                    
                    if progress_callback:
                        progress = (idx + 1) / total_products
                        progress_callback(f"[{idx + 1}/{total_products}] {brand} - {name}", progress)
                    
                    product_code = selected_product.get('상품코드', '')
                    if not product_code:
                        selected_product['상태'] = '상품코드 없음'
                        selected_product['업데이트시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        updated_products.append(selected_product)
                        continue
                    
                    try:
                        product_url = f"https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={product_code}"
                        await page.goto(product_url, wait_until="networkidle", timeout=10000)
                        await asyncio.sleep(1)
                        
                        updated_product = await self._extract_product_from_detail_page(page, selected_product)
                        
                        if updated_product:
                            updated_product = self._update_price_history(selected_product, updated_product)
                            updated_product['업데이트시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            updated_product['상태'] = '업데이트됨'
                            updated_products.append(updated_product)
                        else:
                            selected_product['상태'] = '상품 없음'
                            selected_product['업데이트시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            updated_products.append(selected_product)
                            
                    except Exception as e:
                        selected_product['상태'] = f'오류: {str(e)[:20]}'
                        selected_product['업데이트시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        updated_products.append(selected_product)
                        continue
                            
            except Exception as e:
                if progress_callback:
                    progress_callback(f"업데이트 중 오류 발생: {str(e)}", 1.0)
            finally:
                await browser.close()
        
        return updated_products
    
    async def _extract_product_from_detail_page(self, page, original_product):
        """상품 상세 페이지에서 정보 추출"""
        try:
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            # 브랜드명 추출
            brand = ""
            try:
                brand_elem = await page.query_selector(".prd_brand a")
                if not brand_elem:
                    brand_elem = await page.query_selector(".prd_brand")
                if brand_elem:
                    brand = await brand_elem.inner_text()
                    brand = brand.strip()
            except:
                pass
            if not brand:
                brand = original_product.get('브랜드', '')
            
            # 상품명 추출
            name = ""
            try:
                name_elem = await page.query_selector(".prd_name")
                if name_elem:
                    name = await name_elem.inner_text()
                    name = name.strip()
            except:
                pass
            if not name:
                name = original_product.get('상품명', '')
            
            # 가격 정보 추출
            original_price = ""
            discount_price = ""
            
            try:
                # 할인가
                discount_price_elem = await page.query_selector(".price .price-2 strong")
                if discount_price_elem:
                    discount_price_text = await discount_price_elem.inner_text()
                    discount_price_text = discount_price_text.strip().replace(',', '')
                    if discount_price_text.isdigit():
                        discount_price = f"{int(discount_price_text):,}"
                
                # 정가
                original_price_elem = await page.query_selector(".price .price-1 strike")
                if original_price_elem:
                    original_price_text = await original_price_elem.inner_text()
                    original_price_text = original_price_text.strip().replace(',', '')
                    if original_price_text.isdigit():
                        original_price = f"{int(original_price_text):,}"
                
                # 할인가만 있는 경우
                if discount_price and not original_price:
                    try:
                        price1_elem = await page.query_selector(".price .price-1")
                        if price1_elem:
                            price1_text = await price1_elem.inner_text()
                            if "strike" not in await price1_elem.inner_html():
                                numbers = re.findall(r'[\d,]+', price1_text)
                                if numbers:
                                    price_num = numbers[0].replace(',', '')
                                    if price_num.isdigit():
                                        original_price = f"{int(price_num):,}"
                    except:
                        pass
                
            except Exception as e:
                pass
            
            # 대체 가격 추출 방법
            if not discount_price:
                try:
                    price_selectors = [
                        ".price strong",
                        ".price-2",
                        ".final_price",
                        ".sale_price",
                        ".current_price"
                    ]
                    
                    for selector in price_selectors:
                        elem = await page.query_selector(selector)
                        if elem:
                            text = await elem.inner_text()
                            numbers = re.findall(r'[\d,]+', text)
                            if numbers:
                                price_num = numbers[0].replace(',', '')
                                if price_num.isdigit() and int(price_num) > 100:
                                    discount_price = f"{int(price_num):,}"
                                    break
                except:
                    pass
            
            # 기존 가격 정보 보존
            if not discount_price:
                discount_price = original_product.get('할인가', '')
            if not original_price:
                original_price = original_product.get('원가', '')
            
            # 가격 보정
            if not discount_price and original_price:
                discount_price = original_price
            elif not original_price and discount_price:
                original_price = discount_price
            
            # 이미지 URL 추출
            image_url = ""
            try:
                image_selectors = [
                    ".prd_img img",
                    ".goods_img img", 
                    ".product_img img",
                    ".item_img img",
                    "img[src*='thumbnails']"
                ]
                for selector in image_selectors:
                    img_elem = await page.query_selector(selector)
                    if img_elem:
                        image_url = await img_elem.get_attribute("src")
                        if image_url and ("http" in image_url or image_url.startswith("//")):
                            break
            except:
                pass
            if not image_url:
                image_url = original_product.get('이미지URL', '')
            
            # 상품 정보 구성
            updated_product = {
                '브랜드': brand,
                '상품명': name,
                '원가': original_price,
                '할인가': discount_price,
                '혜택': original_product.get('혜택', ''),
                '검색키워드': original_product.get('검색키워드', ''),
                '상품코드': original_product.get('상품코드', ''),
                '상품URL': original_product.get('상품URL', ''),
                '이미지URL': image_url,
                '가격히스토리': original_product.get('가격히스토리', []),
                '목표가격': original_product.get('목표가격', ''),
                '선택됨': original_product.get('선택됨', False)
            }
            
            return updated_product
            
        except Exception as e:
            return original_product
    
    def _update_price_history(self, old_product, new_product):
        """가격 히스토리 업데이트"""
        price_history = old_product.get('가격히스토리', [])
        
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_original = new_product.get('원가', '')
        current_discount = new_product.get('할인가', '')
        
        if price_history:
            last_entry = price_history[-1]
            if (last_entry.get('원가') != current_original or 
                last_entry.get('할인가') != current_discount):
                price_history.append({
                    '날짜': current_date,
                    '원가': current_original,
                    '할인가': current_discount,
                    '시간': datetime.now().strftime('%H:%M:%S')
                })
        else:
            price_history.append({
                '날짜': current_date,
                '원가': current_original,
                '할인가': current_discount,
                '시간': datetime.now().strftime('%H:%M:%S')
            })
        
        new_product['가격히스토리'] = price_history
        return new_product
    
    async def _scroll_to_load_all(self, page):
        """페이지 스크롤"""
        previous_height = 0
        scroll_attempts = 0
        max_attempts = 5
        
        while scroll_attempts < max_attempts:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == previous_height:
                break
            previous_height = new_height
            scroll_attempts += 1
    
    async def _extract_products(self, page, keyword, page_num):
        """상품 정보 추출"""
        await self._extract_products_to_list(page, keyword, self.products)
    
    async def _extract_products_to_list(self, page, keyword, product_list):
        """상품 정보를 지정된 리스트에 추출"""
        product_elements = await page.query_selector_all("li.flag.li_result")
        
        for element in product_elements:
            try:
                product_info = {}
                
                brand_elem = await element.query_selector(".tx_brand")
                product_info['브랜드'] = await brand_elem.inner_text() if brand_elem else ""
                
                name_elem = await element.query_selector(".tx_name")
                product_info['상품명'] = await name_elem.inner_text() if name_elem else ""
                
                price_section = await element.query_selector(".prd_price")
                if price_section:
                    original_price_elem = await price_section.query_selector(".tx_org .tx_num")
                    product_info['원가'] = await original_price_elem.inner_text() if original_price_elem else ""
                    
                    current_price_elem = await price_section.query_selector(".tx_cur .tx_num")
                    product_info['할인가'] = await current_price_elem.inner_text() if current_price_elem else ""
                
                benefits = []
                benefit_elems = await element.query_selector_all(".prd_flag .icon_flag")
                for benefit_elem in benefit_elems:
                    benefit_text = await benefit_elem.inner_text()
                    benefits.append(benefit_text)
                product_info['혜택'] = ", ".join(benefits)
                
                img_elem = await element.query_selector(".prd_thumb img")
                product_info['이미지URL'] = await img_elem.get_attribute("src") if img_elem else ""
                
                link_elem = await element.query_selector(".prd_thumb")
                href = await link_elem.get_attribute("href") if link_elem else ""
                if href:
                    goods_no_match = re.search(r'goodsNo=([A-Z0-9]+)', href)
                    product_info['상품코드'] = goods_no_match.group(1) if goods_no_match else ""
                    product_info['상품URL'] = f"https://www.oliveyoung.co.kr{href}" if href.startswith('/') else href
                else:
                    product_info['상품코드'] = ""
                    product_info['상품URL'] = ""
                
                product_info['검색키워드'] = keyword
                product_info['선택됨'] = False
                product_info['목표가격'] = ""
                product_info['크롤링시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                current_date = datetime.now().strftime('%Y-%m-%d')
                product_info['가격히스토리'] = [{
                    '날짜': current_date,
                    '원가': product_info['원가'],
                    '할인가': product_info['할인가'],
                    '시간': datetime.now().strftime('%H:%M:%S')
                }]
                
                product_list.append(product_info)
                
            except Exception as e:
                continue

# 세션 상태 초기화
def init_session_state():
    if 'products_data' not in st.session_state:
        st.session_state.products_data = []
    if 'favorites_data' not in st.session_state:
        st.session_state.favorites_data = []
    if 'scraper' not in st.session_state:
        st.session_state.scraper = OliveYoungScraper()
    if 'data_file' not in st.session_state:
        st.session_state.data_file = "oliveyoung_streamlit_data.json"

# 데이터 저장/로드
def save_data():
    try:
        data = {
            'products': st.session_state.products_data,
            'favorites': st.session_state.favorites_data,
            'last_updated': datetime.now().isoformat()
        }
        with open(st.session_state.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"데이터 저장 오류: {e}")
        return False

def load_data():
    try:
        if os.path.exists(st.session_state.data_file):
            with open(st.session_state.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            st.session_state.products_data = data.get('products', [])
            st.session_state.favorites_data = data.get('favorites', [])
            
            last_updated = data.get('last_updated', '')
            if last_updated:
                st.success(f"이전 데이터 로드됨 (마지막 업데이트: {last_updated[:19]})")
            return True
    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")
        return False

# 엑셀 생성 함수들
def create_favorites_excel(favorites_data, selected_only=False):
    """관심상품 엑셀 파일 생성"""
    if selected_only:
        data_to_export = [p for p in favorites_data if p.get('선택됨', False)]
        if not data_to_export:
            return None, "선택된 관심상품이 없습니다."
    else:
        data_to_export = favorites_data
        if not data_to_export:
            return None, "관심상품이 없습니다."
    
    try:
        # 관심상품 데이터 준비
        fav_data = []
        for product in data_to_export:
            export_product = {}
            
            # 기본 정보
            export_product['브랜드'] = product.get('브랜드', '')
            export_product['상품명'] = product.get('상품명', '')
            export_product['현재_원가'] = product.get('원가', '')
            export_product['현재_할인가'] = product.get('할인가', '')
            export_product['목표가격'] = product.get('목표가격', '')
            export_product['혜택'] = product.get('혜택', '')
            export_product['검색키워드'] = product.get('검색키워드', '')
            export_product['상품코드'] = product.get('상품코드', '')
            export_product['상품URL'] = product.get('상품URL', '')
            export_product['최근업데이트'] = product.get('업데이트시간', product.get('크롤링시간', ''))
            export_product['관심상품_추가시간'] = product.get('추가시간', '')
            
            # 목표가격 달성 여부
            if product.get('목표가격', ''):
                try:
                    target_price = int(product.get('목표가격', '').replace(',', ''))
                    current_price_str = product.get('할인가', '').replace(',', '')
                    if current_price_str and current_price_str.isdigit():
                        current_price = int(current_price_str)
                        export_product['목표가격_달성여부'] = '달성' if current_price <= target_price else '미달성'
                        if current_price <= target_price:
                            export_product['할인_금액'] = f"{target_price - current_price:,}원"
                        else:
                            export_product['목표까지_차액'] = f"{current_price - target_price:,}원"
                    else:
                        export_product['목표가격_달성여부'] = '가격정보없음'
                except:
                    export_product['목표가격_달성여부'] = '계산불가'
            else:
                export_product['목표가격_달성여부'] = '목표가격미설정'
            
            # 할인율 계산
            try:
                original = product.get('원가', '').replace(',', '')
                discount = product.get('할인가', '').replace(',', '')
                if original and discount and original != '0' and discount != '0':
                    discount_rate = round((1 - int(discount) / int(original)) * 100, 1)
                    export_product['현재_할인율'] = f"{discount_rate}%"
                else:
                    export_product['현재_할인율'] = "계산불가"
            except:
                export_product['현재_할인율'] = "계산불가"
            
            fav_data.append(export_product)
        
        # 엑셀 파일 생성
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_fav = pd.DataFrame(fav_data)
            sheet_name = '선택된_관심상품' if selected_only else '관심상품_전체'
            df_fav.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # 가격 히스토리
            history_data = []
            for product in data_to_export:
                price_history = product.get('가격히스토리', [])
                if len(price_history) > 1:
                    for entry in price_history:
                        history_entry = {
                            '브랜드': product.get('브랜드', ''),
                            '상품명': product.get('상품명', ''),
                            '날짜': entry.get('날짜', ''),
                            '시간': entry.get('시간', ''),
                            '원가': entry.get('원가', ''),
                            '할인가': entry.get('할인가', '')
                        }
                        history_data.append(history_entry)
            
            if history_data:
                df_history = pd.DataFrame(history_data)
                history_sheet_name = '선택상품_가격히스토리' if selected_only else '가격변화_히스토리'
                df_history.to_excel(writer, sheet_name=history_sheet_name, index=False)
            
            # 목표가격 달성 상품 (전체 내보내기일 때만)
            if not selected_only:
                achieved_products = [p for p in fav_data if p.get('목표가격_달성여부') == '달성']
                if achieved_products:
                    df_achieved = pd.DataFrame(achieved_products)
                    df_achieved.to_excel(writer, sheet_name='목표가격_달성상품', index=False)
        
        output.seek(0)
        return output, None
        
    except Exception as e:
        return None, f"엑셀 파일 생성 오류: {str(e)}"

# 가격 히스토리 차트 생성
def create_price_history_chart(product_data):
    """가격 히스토리 차트 생성"""
    if not PLOTLY_AVAILABLE:
        st.warning("📊 그래프를 보려면 'pip install plotly' 를 설치해주세요")
        return None
    
    price_history = product_data.get('가격히스토리', [])
    
    if len(price_history) < 2:
        st.info("가격 변화 데이터가 충분하지 않습니다. (최소 2회 이상의 업데이트 필요)")
        return None
    
    try:
        dates = []
        original_prices = []
        discount_prices = []
        
        for entry in price_history:
            try:
                date_str = f"{entry.get('날짜', '')} {entry.get('시간', '00:00:00')}"
                date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                dates.append(date_obj)
                
                original = entry.get('원가', '0').replace(',', '')
                discount = entry.get('할인가', '0').replace(',', '')
                
                original_prices.append(int(original) if original and original != '0' else 0)
                discount_prices.append(int(discount) if discount and discount != '0' else 0)
            except:
                continue
        
        if dates and original_prices:
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=dates, 
                y=original_prices,
                mode='lines+markers',
                name='원가',
                line=dict(color='red', width=2),
                marker=dict(size=6)
            ))
            
            fig.add_trace(go.Scatter(
                x=dates, 
                y=discount_prices,
                mode='lines+markers',
                name='할인가',
                line=dict(color='blue', width=2),
                marker=dict(size=6)
            ))
            
            fig.update_layout(
                title=f"가격 변화 - {product_data.get('브랜드', '')} {product_data.get('상품명', '')[:30]}...",
                xaxis_title="날짜",
                yaxis_title="가격 (원)",
                hovermode='x unified',
                width=800,
                height=400
            )
            
            return fig
    except Exception as e:
        st.error(f"그래프 생성 오류: {str(e)}")
        return None

# 메인 앱
def main():
    st.title("🛍️ 올리브영 상품 크롤러")
    st.markdown("---")
    
    # 세션 상태 초기화
    init_session_state()
    
    # 사이드바
    with st.sidebar:
        st.header("⚙️ 설정")
        
        # 검색 설정
        st.subheader("🔍 검색 설정")
        keywords_text = st.text_area(
            "검색어 (쉼표로 구분)",
            value="선크림, 토너, 세럼",
            height=100,
            help="여러 검색어를 쉼표(,)로 구분해서 입력하세요"
        )
        
        max_pages = st.selectbox(
            "크롤링 페이지 수",
            options=[1, 2, 3, 4, 5],
            index=0,
            help="각 검색어당 크롤링할 페이지 수"
        )
        
        # 크롤링 시작 버튼
        if st.button("🚀 크롤링 시작", type="primary", use_container_width=True):
            if keywords_text.strip():
                keywords = [k.strip() for k in keywords_text.split(',') if k.strip()]
                
                # 진행 상황 표시
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(message, progress=None):
                    status_text.text(message)
                    if progress is not None:
                        progress_bar.progress(progress)
                
                # 크롤링 실행
                with st.spinner("크롤링 중..."):
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        products = loop.run_until_complete(
                            st.session_state.scraper.scrape_products(
                                keywords, 
                                max_pages,
                                progress_callback=update_progress
                            )
                        )
                        
                        st.session_state.products_data = products
                        save_data()
                        
                        progress_bar.progress(1.0)
                        status_text.text(f"✅ 크롤링 완료! 총 {len(products)}개 상품")
                        st.success(f"🎉 {len(products)}개 상품을 찾았습니다!")
                        
                    except Exception as e:
                        st.error(f"❌ 크롤링 오류: {str(e)}")
            else:
                st.warning("⚠️ 검색어를 입력해주세요")
        
        st.markdown("---")
        
        # 데이터 관리
        st.subheader("💾 데이터 관리")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 저장", use_container_width=True):
                if save_data():
                    st.success("저장 완료!")
        
        with col2:
            if st.button("📂 로드", use_container_width=True):
                load_data()
        
        # 통계 정보
        st.markdown("---")
        st.subheader("📊 통계")
        st.metric("검색 결과", f"{len(st.session_state.products_data)}개")
        st.metric("관심 상품", f"{len(st.session_state.favorites_data)}개")
        
        if st.session_state.favorites_data:
            target_achieved = len([p for p in st.session_state.favorites_data 
                                 if p.get('목표가격', '') and 
                                 p.get('할인가', '').replace(',', '').isdigit() and
                                 p.get('목표가격', '').replace(',', '').isdigit() and
                                 int(p.get('할인가', '').replace(',', '')) <= int(p.get('목표가격', '').replace(',', ''))])
            st.metric("목표가격 달성", f"{target_achieved}개")
    
    # 메인 영역
    tab1, tab2 = st.tabs(["🔍 검색 결과", "⭐ 관심 상품"])
    
    # 검색 결과 탭
    with tab1:
        st.header("🔍 검색 결과")
        
        if st.session_state.products_data:
            # 검색 결과 표시
            df = pd.DataFrame(st.session_state.products_data)
            
            # 컬럼 선택
            display_columns = ['브랜드', '상품명', '원가', '할인가', '혜택', '검색키워드']
            df_display = df[display_columns].copy()
            
            # 데이터 에디터로 선택 기능 구현
            edited_df = st.data_editor(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "브랜드": st.column_config.TextColumn("브랜드", width="small"),
                    "상품명": st.column_config.TextColumn("상품명", width="large"),
                    "원가": st.column_config.TextColumn("원가", width="small"),
                    "할인가": st.column_config.TextColumn("할인가", width="small"),
                    "혜택": st.column_config.TextColumn("혜택", width="medium"),
                    "검색키워드": st.column_config.TextColumn("검색키워드", width="small")
                }
            )
            
            # 이미지 표시
            st.subheader("🖼️ 상품 이미지")
            
            # 페이지네이션을 위한 설정
            items_per_page = 6
            total_pages = (len(st.session_state.products_data) - 1) // items_per_page + 1
            
            if total_pages > 1:
                page = st.selectbox("페이지 선택", range(1, total_pages + 1), key="search_page")
                start_idx = (page - 1) * items_per_page
                end_idx = start_idx + items_per_page
                products_to_show = st.session_state.products_data[start_idx:end_idx]
            else:
                products_to_show = st.session_state.products_data
            
            # 이미지 그리드 표시
            cols = st.columns(3)
            for idx, product in enumerate(products_to_show):
                col = cols[idx % 3]
                
                with col:
                    # 상품 정보 표시
                    st.markdown(f"**{product.get('브랜드', '')}**")
                    st.markdown(f"{product.get('상품명', '')[:50]}...")
                    
                    # 가격 정보
                    if product.get('할인가', ''):
                        st.markdown(f"💰 **{product.get('할인가', '')}원**")
                    if product.get('원가', '') and product.get('원가', '') != product.get('할인가', ''):
                        st.markdown(f"~~{product.get('원가', '')}원~~")
                    
                    # 이미지 표시
                    image_url = product.get('이미지URL', '')
                    if image_url:
                        try:
                            st.image(image_url, width=200)
                        except:
                            st.info("이미지를 불러올 수 없습니다")
                    
                    # 상품 페이지 링크
                    if product.get('상품URL', ''):
                        st.markdown(f"[🔗 상품 페이지 열기]({product.get('상품URL', '')})")
                    
                    # 관심상품에 추가 버튼
                    if st.button(f"⭐ 관심상품 추가", key=f"add_{idx}_{product.get('상품코드', '')}", use_container_width=True):
                        # 중복 확인
                        brand_name_key = f"{product['브랜드']}_{product['상품명']}"
                        is_duplicate = any(
                            f"{fav_product['브랜드']}_{fav_product['상품명']}" == brand_name_key
                            for fav_product in st.session_state.favorites_data
                        )
                        
                        if not is_duplicate:
                            product_copy = product.copy()
                            product_copy['선택됨'] = False
                            product_copy['목표가격'] = ""
                            product_copy['추가시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            st.session_state.favorites_data.append(product_copy)
                            save_data()
                            st.success("관심상품에 추가되었습니다!")
                            st.rerun()
                        else:
                            st.warning("이미 관심상품에 추가된 상품입니다")
                    
                    st.markdown("---")
            
            # 액션 버튼들
            st.subheader("📋 액션")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("🗑️ 검색 결과 지우기", use_container_width=True):
                    st.session_state.products_data = []
                    save_data()
                    st.rerun()
            
            with col2:
                # 전체 엑셀 다운로드
                if st.session_state.products_data:
                    df_download = pd.DataFrame(st.session_state.products_data)
                    df_download = df_download.drop(columns=['선택됨'], errors='ignore')
                    
                    csv = df_download.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📊 CSV 다운로드",
                        data=csv,
                        file_name=f"올리브영_검색결과_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            with col3:
                if st.button("⭐ 전체 관심상품 추가", use_container_width=True):
                    added_count = 0
                    for product in st.session_state.products_data:
                        brand_name_key = f"{product['브랜드']}_{product['상품명']}"
                        is_duplicate = any(
                            f"{fav_product['브랜드']}_{fav_product['상품명']}" == brand_name_key
                            for fav_product in st.session_state.favorites_data
                        )
                        
                        if not is_duplicate:
                            product_copy = product.copy()
                            product_copy['선택됨'] = False
                            product_copy['목표가격'] = ""
                            product_copy['추가시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            st.session_state.favorites_data.append(product_copy)
                            added_count += 1
                    
                    save_data()
                    st.success(f"{added_count}개 상품이 관심상품에 추가되었습니다!")
                    st.rerun()
        
        else:
            st.info("🔍 검색어를 입력하고 크롤링을 시작해주세요")
    
    # 관심 상품 탭
    with tab2:
        st.header("⭐ 관심 상품")
        
        if st.session_state.favorites_data:
            # 관심상품 관리 버튼들
            st.subheader("🛠️ 관심상품 관리")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("🔄 선택된 상품 새로고침", use_container_width=True):
                    selected_products = [p for p in st.session_state.favorites_data if p.get('선택됨', False)]
                    if selected_products:
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        def update_progress(message, progress=None):
                            status_text.text(message)
                            if progress is not None:
                                progress_bar.progress(progress)
                        
                        with st.spinner("관심상품 새로고침 중..."):
                            try:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                
                                updated_products = loop.run_until_complete(
                                    st.session_state.scraper.scrape_selected_products(
                                        selected_products,
                                        progress_callback=update_progress
                                    )
                                )
                                
                                # 업데이트된 상품들로 교체
                                updated_dict = {f"{p['브랜드']}_{p['상품명']}": p for p in updated_products}
                                
                                for i, product in enumerate(st.session_state.favorites_data):
                                    key = f"{product['브랜드']}_{product['상품명']}"
                                    if key in updated_dict:
                                        st.session_state.favorites_data[i] = updated_dict[key]
                                
                                save_data()
                                progress_bar.progress(1.0)
                                status_text.text("✅ 새로고침 완료!")
                                st.success("관심상품이 새로고침되었습니다!")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"새로고침 오류: {str(e)}")
                    else:
                        st.warning("새로고침할 상품을 선택해주세요")
            
            with col2:
                if st.button("🗑️ 선택된 상품 삭제", use_container_width=True):
                    selected_indices = [i for i, p in enumerate(st.session_state.favorites_data) if p.get('선택됨', False)]
                    if selected_indices:
                        for i in reversed(selected_indices):
                            del st.session_state.favorites_data[i]
                        save_data()
                        st.success(f"{len(selected_indices)}개 상품이 삭제되었습니다!")
                        st.rerun()
                    else:
                        st.warning("삭제할 상품을 선택해주세요")
            
            with col3:
                # 관심상품 전체 엑셀 다운로드
                excel_data, error = create_favorites_excel(st.session_state.favorites_data, selected_only=False)
                if excel_data:
                    st.download_button(
                        label="📊 전체 엑셀 다운로드",
                        data=excel_data,
                        file_name=f"올리브영_관심상품_전체_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                else:
                    st.button("📊 전체 엑셀 다운로드", disabled=True, use_container_width=True, help=error)
            
            with col4:
                # 선택된 관심상품만 엑셀 다운로드
                selected_count = len([p for p in st.session_state.favorites_data if p.get('선택됨', False)])
                if selected_count > 0:
                    excel_data, error = create_favorites_excel(st.session_state.favorites_data, selected_only=True)
                    if excel_data:
                        st.download_button(
                            label=f"📋 선택된 {selected_count}개 다운로드",
                            data=excel_data,
                            file_name=f"올리브영_관심상품_선택_{selected_count}개_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    else:
                        st.button(f"📋 선택된 {selected_count}개 다운로드", disabled=True, use_container_width=True, help=error)
                else:
                    st.button("📋 선택된 상품 다운로드", disabled=True, use_container_width=True, help="선택된 상품이 없습니다")
            
            st.markdown("---")
            
            # 관심상품 리스트 표시
            st.subheader("📋 관심상품 목록")
            
            # 데이터프레임 생성
            favorites_df = pd.DataFrame(st.session_state.favorites_data)
            
            # 선택 컬럼 추가
            favorites_df['선택'] = favorites_df['선택됨'].apply(lambda x: "☑️" if x else "☐")
            
            # 목표가격 달성 표시
            def format_target_price(row):
                target_price = row.get('목표가격', '')
                current_price = row.get('할인가', '').replace(',', '')
                
                if target_price and current_price.isdigit():
                    target_int = int(target_price.replace(',', ''))
                    current_int = int(current_price)
                    if current_int <= target_int:
                        return f"✅ {target_price}원"
                    else:
                        return f"❌ {target_price}원"
                elif target_price:
                    return f"{target_price}원"
                else:
                    return "미설정"
            
            favorites_df['목표가격_표시'] = favorites_df.apply(format_target_price, axis=1)
            
            # 표시할 컬럼 선택
            display_columns = ['선택', '브랜드', '상품명', '원가', '할인가', '목표가격_표시', '혜택', '업데이트시간']
            
            # 데이터 에디터
            edited_favorites = st.data_editor(
                favorites_df[display_columns],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "선택": st.column_config.TextColumn("선택", width="small"),
                    "브랜드": st.column_config.TextColumn("브랜드", width="small"),
                    "상품명": st.column_config.TextColumn("상품명", width="large"),
                    "원가": st.column_config.TextColumn("원가", width="small"),
                    "할인가": st.column_config.TextColumn("할인가", width="small"),
                    "목표가격_표시": st.column_config.TextColumn("목표가격", width="small"),
                    "혜택": st.column_config.TextColumn("혜택", width="medium"),
                    "업데이트시간": st.column_config.TextColumn("업데이트", width="medium")
                }
            )
            
            # 선택 상태 업데이트
            for idx, row in edited_favorites.iterrows():
                if idx < len(st.session_state.favorites_data):
                    st.session_state.favorites_data[idx]['선택됨'] = (row['선택'] == "☑️")
            
            # 상품별 상세 정보 및 관리
            st.subheader("🔍 상품 상세 관리")
            
            # 상품 선택 드롭다운
            product_options = [f"{p.get('브랜드', '')} - {p.get('상품명', '')[:50]}" for p in st.session_state.favorites_data]
            
            if product_options:
                selected_product_idx = st.selectbox(
                    "관리할 상품을 선택하세요",
                    range(len(product_options)),
                    format_func=lambda x: product_options[x]
                )
                
                selected_product = st.session_state.favorites_data[selected_product_idx]
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    # 상품 정보 표시
                    st.markdown(f"**브랜드:** {selected_product.get('브랜드', '')}")
                    st.markdown(f"**상품명:** {selected_product.get('상품명', '')}")
                    st.markdown(f"**현재 원가:** {selected_product.get('원가', '')}원")
                    st.markdown(f"**현재 할인가:** {selected_product.get('할인가', '')}원")
                    
                    # 목표가격 설정
                    current_target = selected_product.get('목표가격', '').replace(',', '').replace('원', '') if selected_product.get('목표가격') else ''
                    
                    target_price = st.text_input(
                        "목표가격 설정 (숫자만 입력)",
                        value=current_target,
                        key=f"target_price_{selected_product_idx}"
                    )
                    
                    col_btn1, col_btn2 = st.columns(2)
                    
                    with col_btn1:
                        if st.button("💾 목표가격 저장", use_container_width=True):
                            if target_price.strip():
                                try:
                                    target_int = int(target_price.replace(',', ''))
                                    if target_int > 0:
                                        st.session_state.favorites_data[selected_product_idx]['목표가격'] = f"{target_int:,}"
                                        save_data()
                                        st.success(f"목표가격이 {target_int:,}원으로 설정되었습니다!")
                                        st.rerun()
                                    else:
                                        st.error("0보다 큰 값을 입력해주세요")
                                except ValueError:
                                    st.error("올바른 숫자를 입력해주세요")
                            else:
                                st.session_state.favorites_data[selected_product_idx]['목표가격'] = ""
                                save_data()
                                st.success("목표가격이 제거되었습니다!")
                                st.rerun()
                    
                    with col_btn2:
                        if st.button("🗑️ 목표가격 제거", use_container_width=True):
                            st.session_state.favorites_data[selected_product_idx]['목표가격'] = ""
                            save_data()
                            st.success("목표가격이 제거되었습니다!")
                            st.rerun()
                    
                    # 상품 페이지 링크
                    if selected_product.get('상품URL', ''):
                        st.markdown(f"[🔗 상품 페이지 열기]({selected_product.get('상품URL', '')})")
                
                with col2:
                    # 상품 이미지 표시
                    image_url = selected_product.get('이미지URL', '')
                    if image_url:
                        try:
                            st.image(image_url, caption=selected_product.get('상품명', ''), width=250)
                        except:
                            st.info("이미지를 불러올 수 없습니다")
                
                # 가격 히스토리 차트
                st.subheader("📈 가격 변화 히스토리")
                
                price_history = selected_product.get('가격히스토리', [])
                
                if len(price_history) >= 2:
                    # 차트 생성
                    fig = create_price_history_chart(selected_product)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # 히스토리 테이블 표시
                    st.subheader("📊 가격 변화 상세")
                    
                    history_data = []
                    for entry in price_history:
                        original = entry.get('원가', '0').replace(',', '')
                        discount = entry.get('할인가', '0').replace(',', '')
                        
                        try:
                            if original and discount and original != '0':
                                discount_rate = round((1 - int(discount) / int(original)) * 100, 1)
                                discount_str = f"{discount_rate}%"
                            else:
                                discount_str = "0%"
                        except:
                            discount_str = "계산불가"
                        
                        history_data.append({
                            '날짜': entry.get('날짜', ''),
                            '시간': entry.get('시간', ''),
                            '원가': entry.get('원가', ''),
                            '할인가': entry.get('할인가', ''),
                            '할인율': discount_str
                        })
                    
                    history_df = pd.DataFrame(history_data)
                    st.dataframe(history_df, use_container_width=True, hide_index=True)
                    
                else:
                    st.info("가격 변화 데이터가 충분하지 않습니다. 상품을 새로고침하여 가격 변화를 추적해보세요.")
        
        else:
            st.info("⭐ 관심상품이 없습니다. 검색 결과에서 상품을 추가해주세요.")

if __name__ == "__main__":
    main()
