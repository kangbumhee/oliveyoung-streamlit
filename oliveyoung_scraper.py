import subprocess
import sys

# ✅ 크롬 브라우저 설치 함수
try:
    from playwright.async_api import async_playwright
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.async_api import async_playwright

# ✅ 실행 시 브라우저 설치 보장 (PyInstaller exe에서도 필요)
def ensure_chromium_installed():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        print(f"Playwright chromium 설치 실패: {e}")

import asyncio
import pandas as pd
from playwright.async_api import async_playwright
import time
import re
from urllib.parse import quote
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from PIL import Image, ImageTk
import requests
from io import BytesIO
import json
import os
from datetime import datetime
import webbrowser

# matplotlib는 선택적 import
try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

class OliveYoungScraper:
    def __init__(self):
        self.base_url = "https://www.oliveyoung.co.kr/store/search/getSearchMain.do"
        self.products = []
        
    async def scrape_products(self, search_keywords, max_pages=1, progress_callback=None, result_callback=None):
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
                            progress_callback(f"'{keyword}' {page_num}페이지 완료 - 총 {len(self.products)}개 상품")
                    
                    if result_callback:
                        result_callback(self.products.copy())
                        
            except Exception as e:
                if progress_callback:
                    progress_callback(f"오류 발생: {str(e)}")
            finally:
                await browser.close()
                
        return self.products
    
    async def scrape_selected_products(self, selected_products, progress_callback=None):
        """선택된 상품들을 상품코드로 직접 접근하여 빠르게 새로고침"""
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
                        progress_callback(f"[{idx + 1}/{total_products}] {brand} - {name}")
                    
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
                            # 상품 정보를 가져올 수 없는 경우 기존 정보 유지
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
                    progress_callback(f"업데이트 중 오류 발생: {str(e)}")
            finally:
                await browser.close()
        
        return updated_products
    
    async def _extract_product_from_detail_page(self, page, original_product):
        """상품 상세 페이지에서 정보 추출 (올리브영 구조 기반)"""
        try:
            # 페이지 로딩 충분히 대기
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
            
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
            
            # 가격 정보 추출 (올리브영 구조 기반)
            original_price = ""
            discount_price = ""
            
            try:
                # 할인가 (price-2 안의 strong 태그)
                discount_price_elem = await page.query_selector(".price .price-2 strong")
                if discount_price_elem:
                    discount_price_text = await discount_price_elem.inner_text()
                    discount_price_text = discount_price_text.strip().replace(',', '')
                    if discount_price_text.isdigit():
                        discount_price = f"{int(discount_price_text):,}"
                        print(f"할인가 추출 성공: {discount_price}")
                
                # 정가 (price-1 안의 strike 태그)
                original_price_elem = await page.query_selector(".price .price-1 strike")
                if original_price_elem:
                    original_price_text = await original_price_elem.inner_text()
                    original_price_text = original_price_text.strip().replace(',', '')
                    if original_price_text.isdigit():
                        original_price = f"{int(original_price_text):,}"
                        print(f"정가 추출 성공: {original_price}")
                
                # 할인가만 있고 정가가 없는 경우 (세일이 아닌 상품)
                if discount_price and not original_price:
                    # price-1이 정가일 수도 있음
                    try:
                        price1_elem = await page.query_selector(".price .price-1")
                        if price1_elem:
                            price1_text = await price1_elem.inner_text()
                            # strike 태그가 없으면 정가로 간주
                            if "strike" not in await price1_elem.inner_html():
                                numbers = re.findall(r'[\d,]+', price1_text)
                                if numbers:
                                    price_num = numbers[0].replace(',', '')
                                    if price_num.isdigit():
                                        original_price = f"{int(price_num):,}"
                    except:
                        pass
                
            except Exception as e:
                print(f"가격 추출 중 오류: {e}")
            
            # 대체 가격 추출 방법 (위 방법이 실패한 경우)
            if not discount_price:
                try:
                    # 다른 가격 패턴들 시도
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
                                    print(f"대체 방법으로 할인가 추출: {discount_price}")
                                    break
                except:
                    pass
            
            # 페이지 전체에서 가격 패턴 찾기 (최후 수단)
            if not discount_price:
                try:
                    page_content = await page.content()
                    # 가격 패턴 찾기 (10,000원 이상의 가격만)
                    price_patterns = re.findall(r'(\d{2,3}(?:,\d{3})*)\s*원', page_content)
                    valid_prices = []
                    for price_str in price_patterns:
                        price_num = int(price_str.replace(',', ''))
                        if 1000 <= price_num <= 1000000:  # 1천원~100만원 사이
                            valid_prices.append(price_num)
                    
                    if valid_prices:
                        # 가장 일반적인 가격대를 할인가로 설정
                        valid_prices.sort(reverse=True)
                        discount_price = f"{valid_prices[0]:,}"
                        print(f"페이지 스캔으로 가격 추출: {discount_price}")
                        
                        # 더 높은 가격이 있으면 정가로 설정
                        if len(valid_prices) > 1 and valid_prices[1] > valid_prices[0]:
                            original_price = f"{valid_prices[1]:,}"
                except:
                    pass
            
            # 기존 가격 정보 보존
            if not discount_price:
                discount_price = original_product.get('할인가', '')
                print(f"기존 할인가 사용: {discount_price}")
            if not original_price:
                original_price = original_product.get('원가', '')
                print(f"기존 정가 사용: {original_price}")
            
            # 가격 보정: 할인가가 없으면 정가를 할인가로
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
                image_url = original_product.get('_이미지URL', '')
            
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
                '_이미지URL': image_url,
                '가격히스토리': original_product.get('가격히스토리', []),
                '목표가격': original_product.get('목표가격', ''),
                '선택됨': original_product.get('선택됨', False)
            }
            
            print(f"상품 정보 추출 완료: {brand} - {name} - 정가:{original_price} - 할인가:{discount_price}")
            return updated_product
            
        except Exception as e:
            print(f"상품 정보 추출 오류: {e}")
            # 오류 발생 시 기존 정보 반환
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
        """페이지를 스크롤하여 모든 상품이 로드되도록 함"""
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
                product_info['_이미지URL'] = await img_elem.get_attribute("src") if img_elem else ""
                
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

class PriceHistoryWindow:
    def __init__(self, parent, product_data):
        self.window = tk.Toplevel(parent)
        self.window.title(f"가격 히스토리 - {product_data.get('상품명', '')}")
        self.window.geometry("800x600")
        self.product_data = product_data
        
        self.setup_ui()
        
    def setup_ui(self):
        info_frame = ttk.Frame(self.window, padding="10")
        info_frame.pack(fill=tk.X)
        
        ttk.Label(info_frame, text=f"브랜드: {self.product_data.get('브랜드', '')}", font=('', 12, 'bold')).pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"상품명: {self.product_data.get('상품명', '')}", font=('', 10)).pack(anchor=tk.W)
        
        table_frame = ttk.LabelFrame(self.window, text="가격 변화 이력", padding="10")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        columns = ('날짜', '시간', '원가', '할인가', '할인율')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=10)
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120, anchor=tk.CENTER)
        
        price_history = self.product_data.get('가격히스토리', [])
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
            
            tree.insert('', tk.END, values=(
                entry.get('날짜', ''),
                entry.get('시간', ''),
                entry.get('원가', ''),
                entry.get('할인가', ''),
                discount_str
            ))
        
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.create_price_chart(price_history)
    
    def create_price_chart(self, price_history):
        """가격 변화 그래프 생성"""
        chart_frame = ttk.LabelFrame(self.window, text="가격 변화 그래프", padding="10")
        chart_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        if len(price_history) < 2:
            ttk.Label(chart_frame, text="가격 변화 데이터가 충분하지 않습니다.\n(최소 2회 이상의 업데이트 필요)").pack(pady=20)
            return
        
        if not MATPLOTLIB_AVAILABLE:
            text_widget = tk.Text(chart_frame, height=8, width=60)
            text_widget.pack(fill=tk.BOTH, expand=True)
            
            text_widget.insert(tk.END, "📈 가격 변화 요약 (그래프 보려면 'pip install matplotlib' 설치)\n")
            text_widget.insert(tk.END, "=" * 60 + "\n\n")
            
            for i, entry in enumerate(price_history):
                original = entry.get('원가', '0').replace(',', '')
                discount = entry.get('할인가', '0').replace(',', '')
                date = entry.get('날짜', '')
                time = entry.get('시간', '')
                
                text_widget.insert(tk.END, f"{i+1}. {date} {time}\n")
                text_widget.insert(tk.END, f"   원가: {entry.get('원가', '')}원\n")
                text_widget.insert(tk.END, f"   할인가: {entry.get('할인가', '')}원\n")
                
                if i > 0:
                    try:
                        prev_discount = int(price_history[i-1].get('할인가', '0').replace(',', ''))
                        curr_discount = int(discount) if discount and discount != '0' else 0
                        if prev_discount != curr_discount:
                            change = curr_discount - prev_discount
                            change_str = f"+{change:,}" if change > 0 else f"{change:,}"
                            text_widget.insert(tk.END, f"   변화: {change_str}원\n")
                    except:
                        pass
                
                text_widget.insert(tk.END, "\n")
            
            text_widget.config(state=tk.DISABLED)
            return
        
        try:
            fig, ax = plt.subplots(figsize=(10, 4))
            
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
                ax.plot(dates, original_prices, 'r-o', label='원가', linewidth=2, markersize=6)
                ax.plot(dates, discount_prices, 'b-o', label='할인가', linewidth=2, markersize=6)
                
                ax.set_xlabel('날짜')
                ax.set_ylabel('가격 (원)')
                ax.legend()
                ax.grid(True, alpha=0.3)
                
                if len(dates) > 1:
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
                    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(dates)//7)))
                
                plt.xticks(rotation=45)
                plt.tight_layout()
                
                canvas = FigureCanvasTkAgg(fig, chart_frame)
                canvas.draw()
                canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
        except Exception as e:
            ttk.Label(chart_frame, text=f"그래프 생성 오류: {str(e)}").pack(pady=20)

class OliveYoungGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("올리브영 상품 크롤러 - 관심상품 관리")
        self.root.geometry("1200x900")
        self.root.configure(bg='#f0f0f0')
        
        self.scraper = OliveYoungScraper()
        self.products_data = []
        self.favorites_data = []
        self.image_cache = {}
        self.image_windows = {}
        self.data_file = "oliveyoung_data.json"
        
        self.setup_ui()
        self.load_data()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        input_frame = ttk.LabelFrame(main_frame, text="검색 설정", padding="10")
        input_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(input_frame, text="검색어 (여러개는 쉼표로 구분):").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        self.keyword_entry = tk.Text(input_frame, height=2, width=60)
        self.keyword_entry.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        self.keyword_entry.insert("1.0", "선크림, 토너, 세럼")
        
        ttk.Label(input_frame, text="크롤링 페이지 수:").grid(row=2, column=0, sticky=tk.W)
        self.page_var = tk.StringVar(value="1")
        page_spinbox = ttk.Spinbox(input_frame, from_=1, to=10, textvariable=self.page_var, width=10)
        page_spinbox.grid(row=2, column=1, sticky=tk.W, padx=(10, 0))
        
        button_frame = ttk.Frame(input_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=(10, 0))
        
        self.start_button = ttk.Button(button_frame, text="크롤링 시작", command=self.start_scraping)
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.add_to_favorites_button = ttk.Button(button_frame, text="관심상품에 추가", command=self.add_to_favorites, state=tk.DISABLED)
        self.add_to_favorites_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.export_button = ttk.Button(button_frame, text="엑셀로 내보내기", command=self.export_to_excel, state=tk.DISABLED)
        self.export_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.clear_button = ttk.Button(button_frame, text="결과 지우기", command=self.clear_results)
        self.clear_button.pack(side=tk.LEFT)
        
        self.progress_var = tk.StringVar(value="대기 중...")
        self.progress_label = ttk.Label(input_frame, textvariable=self.progress_var)
        self.progress_label.grid(row=4, column=0, columnspan=3, pady=(10, 0))
        
        paned_window = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        paned_window.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        
        search_frame = ttk.LabelFrame(paned_window, text="검색 결과", padding="10")
        paned_window.add(search_frame, weight=1)
        
        self.setup_search_results_table(search_frame)
        
        favorites_frame = ttk.LabelFrame(paned_window, text="관심 상품", padding="10")
        paned_window.add(favorites_frame, weight=2)
        
        self.setup_favorites_table(favorites_frame)
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        input_frame.columnconfigure(0, weight=1)
    
    def setup_search_results_table(self, parent):
        """검색 결과 테이블 설정"""
        columns = ('선택', '브랜드', '상품명', '원가', '할인가', '혜택', '검색키워드', '이미지', '상품페이지')
        self.search_tree = ttk.Treeview(parent, columns=columns, show='headings', height=8)
        
        column_widths = {
            '선택': 50,
            '브랜드': 100,
            '상품명': 280,
            '원가': 80,
            '할인가': 80,
            '혜택': 120,
            '검색키워드': 100,
            '이미지': 80,
            '상품페이지': 90
        }
        
        for col in columns:
            self.search_tree.heading(col, text=col)
            self.search_tree.column(col, width=column_widths.get(col, 100), minwidth=50)
        
        self.search_tree.bind('<Button-1>', self.on_search_tree_click)
        
        search_scroll_y = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.search_tree.yview)
        search_scroll_x = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self.search_tree.xview)
        self.search_tree.configure(yscrollcommand=search_scroll_y.set, xscrollcommand=search_scroll_x.set)
        
        self.search_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        search_scroll_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        search_scroll_x.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        search_info_frame = ttk.Frame(parent)
        search_info_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        
        self.search_count_var = tk.StringVar(value="총 0개 상품")
        self.search_count_label = ttk.Label(search_info_frame, textvariable=self.search_count_var)
        self.search_count_label.pack(side=tk.LEFT)
        
        usage_label = ttk.Label(search_info_frame, text="💡 이미지 컬럼: 이미지 보기 | 🔗 상품페이지: 올리브영 페이지 열기", font=('', 8), foreground='gray')
        usage_label.pack(side=tk.LEFT, padx=(20, 0))
        
        self.search_selected_var = tk.StringVar(value="선택 0개")
        self.search_selected_label = ttk.Label(search_info_frame, textvariable=self.search_selected_var)
        self.search_selected_label.pack(side=tk.RIGHT)
        
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
    
    def setup_favorites_table(self, parent):
        """관심 상품 테이블 설정"""
        fav_button_frame = ttk.Frame(parent)
        fav_button_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.refresh_favorites_button = ttk.Button(fav_button_frame, text="선택된 관심상품 새로고침", command=self.refresh_favorites, state=tk.DISABLED)
        self.refresh_favorites_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.remove_favorites_button = ttk.Button(fav_button_frame, text="선택된 항목 제거", command=self.remove_from_favorites, state=tk.DISABLED)
        self.remove_favorites_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.set_target_price_button = ttk.Button(fav_button_frame, text="목표가격 설정", command=self.set_target_price, state=tk.DISABLED)
        self.set_target_price_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.price_history_button = ttk.Button(fav_button_frame, text="가격 히스토리 보기", command=self.show_price_history, state=tk.DISABLED)
        self.price_history_button.pack(side=tk.LEFT)
        
        columns = ('선택', '브랜드', '상품명', '원가', '할인가', '목표가격', '혜택', '검색키워드', '최근업데이트', '이미지', '상품페이지')
        self.favorites_tree = ttk.Treeview(parent, columns=columns, show='headings', height=15)
        
        column_widths = {
            '선택': 50,
            '브랜드': 100,
            '상품명': 220,
            '원가': 80,
            '할인가': 80,
            '목표가격': 80,
            '혜택': 100,
            '검색키워드': 80,
            '최근업데이트': 120,
            '이미지': 80,
            '상품페이지': 90
        }
        
        for col in columns:
            self.favorites_tree.heading(col, text=col)
            self.favorites_tree.column(col, width=column_widths.get(col, 100), minwidth=50)
        
        self.favorites_tree.bind('<Button-1>', self.on_favorites_tree_click)
        self.favorites_tree.bind('<<TreeviewSelect>>', self.on_favorites_tree_select)
        
        fav_scroll_y = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.favorites_tree.yview)
        fav_scroll_x = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self.favorites_tree.xview)
        self.favorites_tree.configure(yscrollcommand=fav_scroll_y.set, xscrollcommand=fav_scroll_x.set)
        
        self.favorites_tree.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        fav_scroll_y.grid(row=1, column=1, sticky=(tk.N, tk.S))
        fav_scroll_x.grid(row=2, column=0, sticky=(tk.W, tk.E))
        
        fav_info_frame = ttk.Frame(parent)
        fav_info_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0))
        
        self.fav_count_var = tk.StringVar(value="총 0개 관심상품")
        self.fav_count_label = ttk.Label(fav_info_frame, textvariable=self.fav_count_var)
        self.fav_count_label.pack(side=tk.LEFT)
        
        usage_label = ttk.Label(fav_info_frame, text="💡 이미지 컬럼: 이미지 보기 | 🔗 상품페이지: 올리브영 페이지 열기 | 🎯 목표가격: 상품 선택 후 설정", font=('', 8), foreground='gray')
        usage_label.pack(side=tk.LEFT, padx=(20, 0))
        
        self.fav_selected_var = tk.StringVar(value="선택 0개")
        self.fav_selected_label = ttk.Label(fav_info_frame, textvariable=self.fav_selected_var)
        self.fav_selected_label.pack(side=tk.RIGHT)
        
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
    
    def on_search_tree_click(self, event):
        """검색 결과 테이블 클릭"""
        region = self.search_tree.identify_region(event.x, event.y)
        if region == "cell":
            item = self.search_tree.identify_row(event.y)
            column = self.search_tree.identify_column(event.x)
            
            if item and column == '#1':  # 선택 컬럼
                self.toggle_search_selection(item)
            elif item and column == '#8':  # 이미지 컬럼
                item_index = self.search_tree.index(item)
                if 0 <= item_index < len(self.products_data):
                    self.show_image_window(f"search_{item_index}", self.products_data[item_index])
            elif item and column == '#9':  # 상품페이지 컬럼
                item_index = self.search_tree.index(item)
                if 0 <= item_index < len(self.products_data):
                    self.open_product_page(self.products_data[item_index])
    
    def on_favorites_tree_click(self, event):
        """관심 상품 테이블 클릭"""
        region = self.favorites_tree.identify_region(event.x, event.y)
        if region == "cell":
            item = self.favorites_tree.identify_row(event.y)
            column = self.favorites_tree.identify_column(event.x)
            
            if item and column == '#1':  # 선택 컬럼
                self.toggle_favorites_selection(item)
            elif item and column == '#10':  # 이미지 컬럼
                item_index = self.favorites_tree.index(item)
                if 0 <= item_index < len(self.favorites_data):
                    self.show_image_window(f"favorites_{item_index}", self.favorites_data[item_index])
            elif item and column == '#11':  # 상품페이지 컬럼
                item_index = self.favorites_tree.index(item)
                if 0 <= item_index < len(self.favorites_data):
                    self.open_product_page(self.favorites_data[item_index])
    
    def toggle_search_selection(self, item):
        """검색 결과 선택 상태 토글"""
        values = list(self.search_tree.item(item, 'values'))
        current_state = values[0]
        
        if current_state == '☑':
            values[0] = '☐'
            selected = False
        else:
            values[0] = '☑'
            selected = True
        
        self.search_tree.item(item, values=values)
        
        item_index = self.search_tree.index(item)
        if 0 <= item_index < len(self.products_data):
            self.products_data[item_index]['선택됨'] = selected
        
        self.update_search_selection_count()
        self.update_add_to_favorites_button_state()
    
    def toggle_favorites_selection(self, item):
        """관심 상품 선택 상태 토글"""
        values = list(self.favorites_tree.item(item, 'values'))
        current_state = values[0]
        
        if current_state == '☑':
            values[0] = '☐'
            selected = False
        else:
            values[0] = '☑'
            selected = True
        
        self.favorites_tree.item(item, values=values)
        
        item_index = self.favorites_tree.index(item)
        if 0 <= item_index < len(self.favorites_data):
            self.favorites_data[item_index]['선택됨'] = selected
        
        self.update_favorites_selection_count()
        self.update_favorites_button_states()
    
    def show_image_window(self, window_key, product_data):
        """이미지 창 표시"""
        # 이미 열린 창이 있으면 닫기
        if window_key in self.image_windows:
            self.image_windows[window_key].destroy()
            del self.image_windows[window_key]
            return
        
        image_url = product_data.get('_이미지URL', '')
        if not image_url:
            messagebox.showinfo("알림", "이미지 URL이 없습니다.")
            return
        
        try:
            # 이미지 로드
            if image_url not in self.image_cache:
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                image = Image.open(BytesIO(response.content))
                image.thumbnail((400, 400), Image.Resampling.LANCZOS)
                self.image_cache[image_url] = ImageTk.PhotoImage(image)
            
            # 새 창 생성
            img_window = tk.Toplevel(self.root)
            img_window.title(f"상품 이미지 - {product_data.get('상품명', '')[:30]}")
            img_window.geometry("450x500")
            img_window.resizable(False, False)
            
            # 상품 정보 표시
            info_frame = ttk.Frame(img_window, padding="10")
            info_frame.pack(fill=tk.X)
            
            ttk.Label(info_frame, text=f"브랜드: {product_data.get('브랜드', '')}", font=('', 11, 'bold')).pack(anchor=tk.W)
            ttk.Label(info_frame, text=f"상품명: {product_data.get('상품명', '')}", font=('', 10), wraplength=400).pack(anchor=tk.W, pady=(5,0))
            
            price_frame = ttk.Frame(info_frame)
            price_frame.pack(fill=tk.X, pady=(5,0))
            
            ttk.Label(price_frame, text=f"할인가: {product_data.get('할인가', '')}원", font=('', 10, 'bold'), foreground='red').pack(side=tk.LEFT)
            if product_data.get('원가', '') and product_data.get('원가', '') != product_data.get('할인가', ''):
                ttk.Label(price_frame, text=f"원가: {product_data.get('원가', '')}원", font=('', 9), foreground='gray').pack(side=tk.RIGHT)
            
            # 목표가격 표시 (관심상품인 경우)
            if product_data.get('목표가격', ''):
                target_frame = ttk.Frame(info_frame)
                target_frame.pack(fill=tk.X, pady=(5,0))
                ttk.Label(target_frame, text=f"목표가격: {product_data.get('목표가격', '')}원", font=('', 10), foreground='blue').pack(side=tk.LEFT)
            
            # 이미지 표시
            img_label = ttk.Label(img_window, image=self.image_cache[image_url])
            img_label.pack(pady=10)
            
            # 닫기 버튼
            close_button = ttk.Button(img_window, text="닫기", command=lambda: self.close_image_window(window_key))
            close_button.pack(pady=10)
            
            # 창 닫힐 때 딕셔너리에서 제거
            def on_close():
                if window_key in self.image_windows:
                    del self.image_windows[window_key]
                img_window.destroy()
            
            img_window.protocol("WM_DELETE_WINDOW", on_close)
            self.image_windows[window_key] = img_window
            
            # 창을 화면 중앙에 배치
            img_window.update_idletasks()
            x = (img_window.winfo_screenwidth() // 2) - (img_window.winfo_width() // 2)
            y = (img_window.winfo_screenheight() // 2) - (img_window.winfo_height() // 2)
            img_window.geometry(f"+{x}+{y}")
            
        except Exception as e:
            messagebox.showerror("오류", f"이미지를 불러올 수 없습니다:\n{str(e)}")
    
    def open_product_page(self, product_data):
        """상품 페이지를 웹브라우저에서 열기"""
        product_url = product_data.get('상품URL', '')
        if not product_url:
            # 상품코드로 URL 생성
            product_code = product_data.get('상품코드', '')
            if product_code:
                product_url = f"https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={product_code}"
        
        if product_url:
            try:
                webbrowser.open(product_url)
                self.progress_var.set(f"상품 페이지 열기: {product_data.get('상품명', '')[:30]}...")
            except Exception as e:
                messagebox.showerror("오류", f"페이지를 열 수 없습니다:\n{str(e)}")
        else:
            messagebox.showwarning("알림", "상품 URL이 없습니다.")

    def close_image_window(self, window_key):
        """이미지 창 닫기"""
        if window_key in self.image_windows:
            self.image_windows[window_key].destroy()
            del self.image_windows[window_key]
    
    def on_favorites_tree_select(self, event):
        """관심상품 테이블 선택 시 버튼 상태 업데이트"""
        self.update_favorites_button_states()
    
    def set_target_price(self):
        """목표가격 설정"""
        selected_items = self.favorites_tree.selection()
        if not selected_items:
            messagebox.showinfo("알림", "목표가격을 설정할 상품을 선택해주세요.")
            return
        
        item = selected_items[0]
        item_index = self.favorites_tree.index(item)
        
        if 0 <= item_index < len(self.favorites_data):
            product = self.favorites_data[item_index]
            
            dialog = tk.Toplevel(self.root)
            dialog.title("목표가격 설정")
            dialog.geometry("500x350")
            dialog.resizable(False, False)
            dialog.grab_set()
            dialog.transient(self.root)
            
            info_frame = ttk.LabelFrame(dialog, text="상품 정보", padding="15")
            info_frame.pack(fill=tk.X, padx=15, pady=15)
            
            ttk.Label(info_frame, text=f"브랜드: {product.get('브랜드', '')}", font=('', 12, 'bold')).pack(anchor=tk.W)
            ttk.Label(info_frame, text=f"상품명: {product.get('상품명', '')}", font=('', 10), wraplength=450).pack(anchor=tk.W, pady=(8,0))
            
            price_info_frame = ttk.Frame(info_frame)
            price_info_frame.pack(fill=tk.X, pady=(10,0))
            
            current_price = product.get('할인가', '').replace(',', '')
            original_price = product.get('원가', '').replace(',', '')
            
            ttk.Label(price_info_frame, text=f"현재 할인가: {product.get('할인가', '')}원", font=('', 11, 'bold'), foreground='red').pack(anchor=tk.W)
            if product.get('원가', '') and product.get('원가', '') != product.get('할인가', ''):
                ttk.Label(price_info_frame, text=f"정가: {product.get('원가', '')}원", font=('', 10), foreground='gray').pack(anchor=tk.W, pady=(3,0))
            
            target_frame = ttk.LabelFrame(dialog, text="목표가격 설정", padding="15")
            target_frame.pack(fill=tk.X, padx=15, pady=(0,15))
            
            ttk.Label(target_frame, text="목표가격 (원):", font=('', 11)).pack(anchor=tk.W)
            
            current_target = product.get('목표가격', '').replace(',', '').replace('원', '') if product.get('목표가격') else ''
            target_price_var = tk.StringVar(value=current_target)
            target_entry = ttk.Entry(target_frame, textvariable=target_price_var, font=('', 14), width=20)
            target_entry.pack(fill=tk.X, pady=(8,0))
            target_entry.focus()
            
            # 빠른 설정 버튼들
            if current_price and current_price.isdigit():
                quick_frame = ttk.Frame(target_frame)
                quick_frame.pack(fill=tk.X, pady=(15,0))
                
                ttk.Label(quick_frame, text="빠른 설정:", font=('', 10)).pack(anchor=tk.W)
                
                button_frame1 = ttk.Frame(quick_frame)
                button_frame1.pack(fill=tk.X, pady=(8,0))
                
                current_int = int(current_price)
                
                # 현재가격
                ttk.Button(button_frame1, text=f"현재가격\n{current_price}원", 
                          command=lambda: target_price_var.set(current_price)).pack(side=tk.LEFT, padx=(0,8))
                
                # 5% 할인
                discount_5 = int(current_int * 0.95)
                ttk.Button(button_frame1, text=f"5% 할인\n{discount_5:,}원", 
                          command=lambda: target_price_var.set(str(discount_5))).pack(side=tk.LEFT, padx=(0,8))
                
                # 10% 할인
                discount_10 = int(current_int * 0.90)
                ttk.Button(button_frame1, text=f"10% 할인\n{discount_10:,}원", 
                          command=lambda: target_price_var.set(str(discount_10))).pack(side=tk.LEFT, padx=(0,8))
                
                button_frame2 = ttk.Frame(quick_frame)
                button_frame2.pack(fill=tk.X, pady=(8,0))
                
                # 15% 할인
                discount_15 = int(current_int * 0.85)
                ttk.Button(button_frame2, text=f"15% 할인\n{discount_15:,}원", 
                          command=lambda: target_price_var.set(str(discount_15))).pack(side=tk.LEFT, padx=(0,8))
                
                # 20% 할인
                discount_20 = int(current_int * 0.80)
                ttk.Button(button_frame2, text=f"20% 할인\n{discount_20:,}원", 
                          command=lambda: target_price_var.set(str(discount_20))).pack(side=tk.LEFT, padx=(0,8))
                
                # 목표가격 제거
                ttk.Button(button_frame2, text="목표가격\n제거", 
                          command=lambda: target_price_var.set("")).pack(side=tk.LEFT)
            
            button_frame = ttk.Frame(dialog)
            button_frame.pack(fill=tk.X, padx=15, pady=15)
            
            def save_target():
                target_text = target_price_var.get().strip()
                if not target_text:
                    self.favorites_data[item_index]['목표가격'] = ""
                    messagebox.showinfo("완료", "목표가격이 제거되었습니다.")
                else:
                    try:
                        target_price = int(target_text.replace(',', ''))
                        if target_price <= 0:
                            messagebox.showerror("오류", "목표가격은 0보다 큰 값을 입력해주세요.")
                            return
                        self.favorites_data[item_index]['목표가격'] = f"{target_price:,}"
                        messagebox.showinfo("완료", f"목표가격이 {target_price:,}원으로 설정되었습니다.")
                    except ValueError:
                        messagebox.showerror("오류", "올바른 숫자를 입력해주세요.")
                        return
                
                self.display_favorites()
                self.save_data()
                dialog.destroy()
            
            ttk.Button(button_frame, text="저장", command=save_target).pack(side=tk.RIGHT, padx=(5,0))
            ttk.Button(button_frame, text="취소", command=dialog.destroy).pack(side=tk.RIGHT)
            
            dialog.bind('<Return>', lambda e: save_target())
            
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
            y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
    
    def start_scraping(self):
        """크롤링 시작"""
        keywords_text = self.keyword_entry.get("1.0", tk.END).strip()
        if not keywords_text:
            messagebox.showwarning("경고", "검색어를 입력해주세요.")
            return
        
        keywords = [k.strip() for k in keywords_text.split(',') if k.strip()]
        max_pages = int(self.page_var.get())
        
        self.start_button.config(state=tk.DISABLED)
        self.add_to_favorites_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        
        thread = threading.Thread(target=self.run_scraping, args=(keywords, max_pages))
        thread.daemon = True
        thread.start()
    
    def run_scraping(self, keywords, max_pages):
        """크롤링 실행"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            products = loop.run_until_complete(
                self.scraper.scrape_products(
                    keywords, 
                    max_pages, 
                    progress_callback=self.update_progress,
                    result_callback=self.update_search_results
                )
            )
            
            self.root.after(0, self.scraping_complete, products)
            
        except Exception as e:
            self.root.after(0, self.scraping_error, str(e))
    
    def update_progress(self, message):
        """진행상황 업데이트"""
        self.root.after(0, lambda: self.progress_var.set(message))
    
    def update_search_results(self, products):
        """검색 결과 업데이트"""
        self.root.after(0, lambda: self.display_search_results(products))
    
    def display_search_results(self, products):
        """검색 결과 표시"""
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)
        
        self.products_data = products
        
        for product in products:
            checkbox = '☑' if product.get('선택됨', False) else '☐'
            values = (
                checkbox,
                product.get('브랜드', ''),
                product.get('상품명', ''),
                product.get('원가', ''),
                product.get('할인가', ''),
                product.get('혜택', ''),
                product.get('검색키워드', ''),
                '이미지보기',
                '페이지열기'
            )
            self.search_tree.insert('', tk.END, values=values)
        
        self.search_count_var.set(f"총 {len(products)}개 상품")
        self.update_search_selection_count()
    
    def display_favorites(self):
        """관심상품 표시"""
        for item in self.favorites_tree.get_children():
            self.favorites_tree.delete(item)
        
        for product in self.favorites_data:
            checkbox = '☑' if product.get('선택됨', False) else '☐'
            
            target_price = product.get('목표가격', '')
            if not target_price:
                target_price = "미설정"
            else:
                target_price = f"{target_price}원"
            
            values = (
                checkbox,
                product.get('브랜드', ''),
                product.get('상품명', ''),
                product.get('원가', ''),
                product.get('할인가', ''),
                target_price,
                product.get('혜택', ''),
                product.get('검색키워드', ''),
                product.get('업데이트시간', product.get('크롤링시간', '')),
                '이미지보기',
                '페이지열기'
            )
            
            item_id = self.favorites_tree.insert('', tk.END, values=values)
            
            if target_price != "미설정":
                try:
                    target_int = int(product.get('목표가격', '').replace(',', ''))
                    current_price_str = product.get('할인가', '').replace(',', '')
                    if current_price_str and current_price_str.isdigit():
                        current_int = int(current_price_str)
                        
                        if current_int <= target_int:
                            self.favorites_tree.set(item_id, '목표가격', f"✅ {target_price}")
                except:
                    pass
        
        self.fav_count_var.set(f"총 {len(self.favorites_data)}개 관심상품")
        self.update_favorites_selection_count()
    
    def scraping_complete(self, products):
        """크롤링 완료"""
        self.display_search_results(products)
        self.progress_var.set(f"크롤링 완료! 총 {len(products)}개 상품")
        self.start_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.NORMAL)
        self.update_add_to_favorites_button_state()
        self.save_data()
    
    def scraping_error(self, error_msg):
        """크롤링 오류"""
        self.progress_var.set(f"오류 발생: {error_msg}")
        self.start_button.config(state=tk.NORMAL)
        self.update_add_to_favorites_button_state()
        self.update_favorites_button_states()
        messagebox.showerror("오류", f"크롤링 중 오류가 발생했습니다:\n{error_msg}")
    
    def update_search_selection_count(self):
        """검색 결과 선택 개수 업데이트"""
        selected_count = sum(1 for p in self.products_data if p.get('선택됨', False))
        self.search_selected_var.set(f"선택 {selected_count}개")
    
    def update_favorites_selection_count(self):
        """관심상품 선택 개수 업데이트"""
        selected_count = sum(1 for p in self.favorites_data if p.get('선택됨', False))
        self.fav_selected_var.set(f"선택 {selected_count}개")
    
    def update_add_to_favorites_button_state(self):
        """관심상품 추가 버튼 상태 업데이트"""
        selected_count = sum(1 for p in self.products_data if p.get('선택됨', False))
        if selected_count > 0:
            self.add_to_favorites_button.config(state=tk.NORMAL)
        else:
            self.add_to_favorites_button.config(state=tk.DISABLED)
    
    def update_favorites_button_states(self):
        """관심상품 관련 버튼 상태 업데이트"""
        selected_count = sum(1 for p in self.favorites_data if p.get('선택됨', False))
        selection = self.favorites_tree.selection()
        
        if selected_count > 0:
            self.refresh_favorites_button.config(state=tk.NORMAL)
            self.remove_favorites_button.config(state=tk.NORMAL)
        else:
            self.refresh_favorites_button.config(state=tk.DISABLED)
            self.remove_favorites_button.config(state=tk.DISABLED)
        
        if len(selection) == 1:
            self.price_history_button.config(state=tk.NORMAL)
            self.set_target_price_button.config(state=tk.NORMAL)
        else:
            self.price_history_button.config(state=tk.DISABLED)
            self.set_target_price_button.config(state=tk.DISABLED)
    
    def add_to_favorites(self):
        """선택된 항목을 관심상품에 추가"""
        selected_products = [p for p in self.products_data if p.get('선택됨', False)]
        if not selected_products:
            messagebox.showinfo("알림", "관심상품에 추가할 항목을 선택해주세요.")
            return
        
        added_count = 0
        for product in selected_products:
            brand_name_key = f"{product['브랜드']}_{product['상품명']}"
            
            is_duplicate = False
            for fav_product in self.favorites_data:
                if f"{fav_product['브랜드']}_{fav_product['상품명']}" == brand_name_key:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                product_copy = product.copy()
                product_copy['선택됨'] = False
                product_copy['목표가격'] = ""
                product_copy['추가시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.favorites_data.append(product_copy)
                added_count += 1
        
        self.display_favorites()
        messagebox.showinfo("완료", f"{added_count}개 상품이 관심상품에 추가되었습니다.")
        self.save_data()
    
    def remove_from_favorites(self):
        """선택된 관심상품 제거"""
        selected_indices = []
        for i, product in enumerate(self.favorites_data):
            if product.get('선택됨', False):
                selected_indices.append(i)
        
        if not selected_indices:
            messagebox.showinfo("알림", "제거할 관심상품을 선택해주세요.")
            return
        
        for i in reversed(selected_indices):
            del self.favorites_data[i]
        
        self.display_favorites()
        messagebox.showinfo("완료", f"{len(selected_indices)}개 관심상품이 제거되었습니다.")
        self.save_data()
    
    def refresh_favorites(self):
        """선택된 관심상품들 새로고침"""
        selected_products = [p for p in self.favorites_data if p.get('선택됨', False)]
        if not selected_products:
            messagebox.showinfo("알림", "새로고침할 관심상품을 선택해주세요.")
            return
        
        self.refresh_favorites_button.config(state=tk.DISABLED)
        self.remove_favorites_button.config(state=tk.DISABLED)
        self.price_history_button.config(state=tk.DISABLED)
        
        thread = threading.Thread(target=self.run_favorites_refresh, args=(selected_products,))
        thread.daemon = True
        thread.start()
    
    def show_price_history(self):
        """선택된 상품의 가격 히스토리 보기"""
        selected_items = self.favorites_tree.selection()
        if not selected_items:
            messagebox.showinfo("알림", "가격 히스토리를 볼 상품을 선택해주세요.")
            return
        
        item = selected_items[0]
        item_index = self.favorites_tree.index(item)
        
        if 0 <= item_index < len(self.favorites_data):
            product = self.favorites_data[item_index]
            PriceHistoryWindow(self.root, product)
    
    def run_favorites_refresh(self, selected_products):
        """관심상품 새로고침 실행"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            updated_products = loop.run_until_complete(
                self.scraper.scrape_selected_products(
                    selected_products,
                    progress_callback=self.update_progress
                )
            )
            
            self.root.after(0, self.favorites_refresh_complete, updated_products)
            
        except Exception as e:
            self.root.after(0, self.scraping_error, str(e))
    
    def favorites_refresh_complete(self, updated_products):
        """관심상품 새로고침 완료"""
        updated_dict = {f"{p['브랜드']}_{p['상품명']}": p for p in updated_products}
        
        for i, product in enumerate(self.favorites_data):
            key = f"{product['브랜드']}_{product['상품명']}"
            if key in updated_dict:
                self.favorites_data[i] = updated_dict[key]
        
        self.display_favorites()
        self.progress_var.set("관심상품 새로고침 완료!")
        self.update_favorites_button_states()
        self.save_data()
    
    def export_to_excel(self):
        """엑셀로 내보내기"""
        if not self.products_data and not self.favorites_data:
            messagebox.showinfo("알림", "내보낼 데이터가 없습니다.")
            return
        
        filename = filedialog.asksaveasfilename(
            title="엑셀 파일 저장",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialname=f"올리브영_검색결과_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        
        if filename:
            try:
                with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                    if self.products_data:
                        search_data = []
                        for product in self.products_data:
                            export_product = {k: v for k, v in product.items() 
                                            if not k.startswith('_') and k != '선택됨'}
                            search_data.append(export_product)
                        
                        df_search = pd.DataFrame(search_data)
                        df_search.to_excel(writer, sheet_name='검색결과', index=False)
                    
                    if self.favorites_data:
                        fav_data = []
                        for product in self.favorites_data:
                            export_product = {k: v for k, v in product.items() 
                                            if not k.startswith('_') and k != '선택됨'}
                            fav_data.append(export_product)
                        
                        df_fav = pd.DataFrame(fav_data)
                        df_fav.to_excel(writer, sheet_name='관심상품', index=False)
                
                messagebox.showinfo("완료", f"엑셀 파일이 저장되었습니다:\n{filename}")
            except Exception as e:
                messagebox.showerror("오류", f"파일 저장 중 오류가 발생했습니다:\n{str(e)}")
    
    def clear_results(self):
        """검색 결과 지우기"""
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)
        
        for window in list(self.image_windows.values()):
            window.destroy()
        self.image_windows.clear()
        
        self.products_data = []
        self.search_count_var.set("총 0개 상품")
        self.search_selected_var.set("선택 0개")
        self.progress_var.set("대기 중...")
        self.export_button.config(state=tk.DISABLED if not self.favorites_data else tk.NORMAL)
        self.add_to_favorites_button.config(state=tk.DISABLED)
    
    def save_data(self):
        """데이터 저장"""
        try:
            data = {
                'products': self.products_data,
                'favorites': self.favorites_data,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"데이터 저장 오류: {e}")
    
    def load_data(self):
        """데이터 로드"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.products_data = data.get('products', [])
                self.favorites_data = data.get('favorites', [])
                
                if self.products_data:
                    self.display_search_results(self.products_data)
                    self.export_button.config(state=tk.NORMAL)
                
                if self.favorites_data:
                    self.display_favorites()
                    self.export_button.config(state=tk.NORMAL)
                
                last_updated = data.get('last_updated', '')
                if last_updated:
                    self.progress_var.set(f"이전 데이터 로드됨 (마지막 업데이트: {last_updated[:19]})")
        except Exception as e:
            print(f"데이터 로드 오류: {e}")
    
    def on_closing(self):
        """프로그램 종료"""
        for window in list(self.image_windows.values()):
            try:
                window.destroy()
            except:
                pass
        
        self.save_data()
        self.root.destroy()

def main():
    try:
        import playwright
        import pandas as pd
        import openpyxl
        from PIL import Image, ImageTk
        import requests
    except ImportError as e:
        print("필요한 라이브러리가 설치되지 않았습니다.")
        print("다음 명령어로 설치해주세요:")
        print("pip install playwright pandas openpyxl pillow requests")
        print("playwright install")
        print("\n선택사항 (가격 그래프 기능):")
        print("pip install matplotlib")
        return

    ensure_chromium_installed()  # ✅ 실행 시 브라우저 설치 확인

    root = tk.Tk()
    app = OliveYoungGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()