import streamlit as st  # ✅ 가장 위에 있어야 함
st.set_page_config(  # ✅ Streamlit 관련 첫 번째 명령어여야 함
    page_title="올리브영 상품 크롤러",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 필수 라이브러리들
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from urllib.parse import quote, urljoin
from datetime import datetime
import json
import os
import io

# 선택적 라이브러리들
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    st.warning("📊 그래프 기능을 사용할 수 없습니다. plotly가 설치되지 않았습니다.")

class OliveYoungScraper:
    def __init__(self):
        # 모바일과 데스크톱 URL 모두 시도
        self.urls = {
            'mobile_search': "https://m.oliveyoung.co.kr/m/search/searchList.do",
            'desktop_search': "https://www.oliveyoung.co.kr/store/search/getSearchMain.do",
            'api_search': "https://www.oliveyoung.co.kr/api/search/searchList"
        }
        self.products = []
        self.session = requests.Session()
        
        # 실제 브라우저처럼 보이도록 헤더 설정
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Referer': 'https://www.oliveyoung.co.kr/',
            'DNT': '1'
        })
        
        # 쿠키 사전 설정
        self._init_session()
    
    def _init_session(self):
        """세션 초기화 - 메인 페이지 방문으로 쿠키 설정"""
        try:
            # 메인 페이지 방문으로 쿠키 획득
            main_urls = [
                'https://www.oliveyoung.co.kr',
                'https://m.oliveyoung.co.kr'
            ]
            
            for url in main_urls:
                try:
                    response = self.session.get(url, timeout=10)
                    if response.status_code == 200:
                        break
                except:
                    continue
                    
            # 추가 헤더 설정
            self.session.headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
            })
            
        except Exception as e:
            pass
        
    def scrape_products(self, search_keywords, max_pages=1, progress_callback=None):
        """올리브영에서 여러 검색어로 상품 정보를 크롤링"""
        self.products = []
        
        try:
            total_keywords = len(search_keywords)
            
            for keyword_idx, keyword in enumerate(search_keywords):
                if progress_callback:
                    progress_callback(f"'{keyword}' 검색 중... ({keyword_idx + 1}/{total_keywords})")
                
                for page_num in range(1, max_pages + 1):
                    if progress_callback:
                        progress_callback(f"'{keyword}' {page_num}페이지 검색 중...")
                    
                    # 다양한 URL 패턴 시도
                    success = False
                    
                    # 1. 모바일 URL 시도
                    mobile_params = {
                        'query': keyword,
                        'page': page_num,
                        'listType': 'list'
                    }
                    
                    success = self._try_search_url(
                        self.urls['mobile_search'],
                        mobile_params,
                        keyword,
                        page_num,
                        progress_callback,
                        "모바일"
                    )
                    
                    # 2. 데스크톱 URL 시도 (모바일 실패시)
                    if not success:
                        desktop_params = {
                            'query': keyword,
                            'page': page_num,
                            'giftYn': 'N',
                            't_page': '통합',
                            't_click': '검색창',
                            't_search_name': '검색'
                        }
                        
                        success = self._try_search_url(
                            self.urls['desktop_search'],
                            desktop_params,
                            keyword,
                            page_num,
                            progress_callback,
                            "데스크톱"
                        )
                    
                    # 3. POST 방식 시도 (GET 실패시)
                    if not success:
                        success = self._try_post_search(
                            keyword,
                            page_num,
                            progress_callback
                        )
                    
                    if progress_callback:
                        progress = (keyword_idx * max_pages + page_num) / (total_keywords * max_pages)
                        status = "성공" if success else "실패"
                        progress_callback(f"'{keyword}' {page_num}페이지 {status} - 총 {len(self.products)}개 상품", progress)
                    
                    # 요청 간격 조절
                    time.sleep(2)
                        
        except Exception as e:
            if progress_callback:
                progress_callback(f"크롤링 중 전체 오류: {str(e)}", 1.0)
                
        return self.products
    
    def _try_search_url(self, url, params, keyword, page_num, progress_callback, method_name):
        """특정 URL로 검색 시도"""
        try:
            if progress_callback:
                progress_callback(f"{method_name} 방식으로 '{keyword}' 검색 중...")
            
            response = self.session.get(url, params=params, timeout=15)
            
            if progress_callback:
                progress_callback(f"{method_name} 응답: {response.status_code}")
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 응답 내용 디버깅
                if progress_callback:
                    progress_callback(f"HTML 길이: {len(response.text)} bytes")
                
                extracted_count = self._extract_products(soup, keyword)
                
                if extracted_count > 0:
                    if progress_callback:
                        progress_callback(f"{method_name} 성공: {extracted_count}개 상품 추출")
                    return True
                else:
                    if progress_callback:
                        progress_callback(f"{method_name} 실패: 상품 추출 불가")
                    
            return False
            
        except Exception as e:
            if progress_callback:
                progress_callback(f"{method_name} 오류: {str(e)}")
            return False
    
    def _try_post_search(self, keyword, page_num, progress_callback):
        """POST 방식으로 검색 시도"""
        try:
            if progress_callback:
                progress_callback(f"POST 방식으로 '{keyword}' 검색 중...")
            
            # POST 데이터
            post_data = {
                'searchWord': keyword,
                'page': page_num,
                'sort': 'default'
            }
            
            # POST 요청
            response = self.session.post(
                self.urls['desktop_search'],
                data=post_data,
                timeout=15
            )
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                extracted_count = self._extract_products(soup, keyword)
                
                if extracted_count > 0:
                    if progress_callback:
                        progress_callback(f"POST 성공: {extracted_count}개 상품 추출")
                    return True
            
            return False
            
        except Exception as e:
            if progress_callback:
                progress_callback(f"POST 오류: {str(e)}")
            return False
    
    def scrape_selected_products(self, selected_products, progress_callback=None):
        """선택된 상품들을 새로고침"""
        updated_products = []
        
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
                    response = self.session.get(product_url, timeout=10)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    updated_product = self._extract_product_from_detail_page(soup, selected_product)
                    
                    if updated_product:
                        updated_product = self._update_price_history(selected_product, updated_product)
                        updated_product['업데이트시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        updated_product['상태'] = '업데이트됨'
                        updated_products.append(updated_product)
                    else:
                        selected_product['상태'] = '상품 없음'
                        selected_product['업데이트시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        updated_products.append(selected_product)
                        
                    # 요청 간격 조절
                    time.sleep(0.5)
                        
                except Exception as e:
                    selected_product['상태'] = f'오류: {str(e)[:20]}'
                    selected_product['업데이트시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    updated_products.append(selected_product)
                    continue
                        
        except Exception as e:
            if progress_callback:
                progress_callback(f"업데이트 중 오류 발생: {str(e)}", 1.0)
        
        return updated_products
    
    def _extract_product_from_detail_page(self, soup, original_product):
        """상품 상세 페이지에서 정보 추출"""
        try:
            # 브랜드명 추출
            brand = ""
            brand_elem = soup.select_one(".prd_brand a")
            if not brand_elem:
                brand_elem = soup.select_one(".prd_brand")
            if brand_elem:
                brand = brand_elem.get_text(strip=True)
            if not brand:
                brand = original_product.get('브랜드', '')
            
            # 상품명 추출
            name = ""
            name_elem = soup.select_one(".prd_name")
            if name_elem:
                name = name_elem.get_text(strip=True)
            if not name:
                name = original_product.get('상품명', '')
            
            # 가격 정보 추출
            original_price = ""
            discount_price = ""
            
            # 할인가
            discount_price_elem = soup.select_one(".price .price-2 strong")
            if discount_price_elem:
                discount_price_text = discount_price_elem.get_text(strip=True).replace(',', '')
                if discount_price_text.isdigit():
                    discount_price = f"{int(discount_price_text):,}"
            
            # 정가
            original_price_elem = soup.select_one(".price .price-1 strike")
            if original_price_elem:
                original_price_text = original_price_elem.get_text(strip=True).replace(',', '')
                if original_price_text.isdigit():
                    original_price = f"{int(original_price_text):,}"
            
            # 할인가만 있는 경우
            if discount_price and not original_price:
                price1_elem = soup.select_one(".price .price-1")
                if price1_elem:
                    price1_text = price1_elem.get_text(strip=True)
                    if "strike" not in str(price1_elem):
                        numbers = re.findall(r'[\d,]+', price1_text)
                        if numbers:
                            price_num = numbers[0].replace(',', '')
                            if price_num.isdigit():
                                original_price = f"{int(price_num):,}"
            
            # 대체 가격 추출 방법
            if not discount_price:
                price_selectors = [
                    ".price strong",
                    ".price-2",
                    ".final_price",
                    ".sale_price",
                    ".current_price"
                ]
                
                for selector in price_selectors:
                    elem = soup.select_one(selector)
                    if elem:
                        text = elem.get_text(strip=True)
                        numbers = re.findall(r'[\d,]+', text)
                        if numbers:
                            price_num = numbers[0].replace(',', '')
                            if price_num.isdigit() and int(price_num) > 100:
                                discount_price = f"{int(price_num):,}"
                                break
            
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
            image_selectors = [
                ".prd_img img",
                ".goods_img img", 
                ".product_img img",
                ".item_img img",
                "img[src*='thumbnails']"
            ]
            for selector in image_selectors:
                img_elem = soup.select_one(selector)
                if img_elem:
                    image_url = img_elem.get('src', '')
                    if image_url and ("http" in image_url or image_url.startswith("//")):
                        break
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
    
    def _extract_products(self, soup, keyword):
        """상품 정보 추출 - 데스크톱/모바일 모두 대응"""
        extracted_count = 0
        
        # 다양한 상품 리스트 셀렉터 시도 (데스크톱 + 모바일)
        product_selectors = [
            # 데스크톱 버전
            "li.flag.li_result",
            "li.li_result",
            ".prd_list li",
            ".search_item",
            ".item_box",
            "[data-attr*='prd']",
            ".product_item",
            ".goods_list li",
            # 모바일 버전
            ".prd_item",
            ".goods_item", 
            ".item",
            ".product",
            "[class*='item']",
            "[class*='product']",
            "[class*='goods']",
            # 일반적인 상품 컨테이너
            "[data-goodsno]",
            "[data-goods-no]",
            "[data-prd-no]"
        ]
        
        product_elements = []
        used_selector = None
        
        # 각 셀렉터를 순서대로 시도
        for selector in product_selectors:
            elements = soup.select(selector)
            if elements and len(elements) > 0:
                product_elements = elements
                used_selector = selector
                break
        
        # 셀렉터로 찾지 못한 경우, 패턴 매칭으로 찾기
        if not product_elements:
            # 상품 관련 클래스명을 가진 모든 요소 찾기
            all_elements = soup.find_all(attrs={"class": re.compile(r"(prd|product|item|goods)", re.I)})
            if all_elements:
                product_elements = all_elements[:20]  # 최대 20개만
                used_selector = "pattern_matching"
        
        # 여전히 찾지 못한 경우, div나 li 요소 중에서 찾기
        if not product_elements:
            potential_elements = soup.find_all(['li', 'div'], limit=50)
            for elem in potential_elements:
                # 상품 정보가 있을 것 같은 요소 찾기
                if (elem.find(string=re.compile(r'원|won|\d+,\d+', re.I)) and 
                    (elem.find('img') or elem.find(string=re.compile(r'[가-힣]{2,}', re.I)))):
                    product_elements.append(elem)
                    if len(product_elements) >= 20:
                        break
            used_selector = "fallback_search"
        
        # 상품 정보 추출
        for element in product_elements:
            try:
                product_info = self._extract_single_product(element, keyword)
                
                # 최소한의 정보가 있을 때만 추가
                if (product_info and 
                    (product_info.get('상품명') or product_info.get('브랜드')) and
                    (product_info.get('할인가') or product_info.get('원가'))):
                    
                    self.products.append(product_info)
                    extracted_count += 1
                
            except Exception as e:
                continue
        
        return extracted_count
    
    def _extract_single_product(self, element, keyword):
        """단일 상품 정보 추출"""
        try:
            product_info = {}
            
            # 브랜드 추출 - 다양한 셀렉터 시도
            brand = self._extract_text_by_selectors(element, [
                ".tx_brand", ".brand", ".prd_brand", ".brand_name",
                "[class*='brand']", ".maker", ".company",
                # 모바일 버전
                ".item_brand", ".goods_brand", ".prod_brand"
            ])
            product_info['브랜드'] = brand
            
            # 상품명 추출
            name = self._extract_text_by_selectors(element, [
                ".tx_name", ".name", ".prd_name", ".title", ".product_name",
                "[class*='name']", "[class*='title']", "h3", "h4",
                # 모바일 버전
                ".item_name", ".goods_name", ".prod_name", ".item_title"
            ])
            product_info['상품명'] = name
            
            # 가격 정보 추출
            price_info = self._extract_price_info(element)
            product_info.update(price_info)
            
            # 혜택 정보 추출
            benefits = self._extract_benefits(element)
            product_info['혜택'] = benefits
            
            # 이미지 URL 추출
            image_url = self._extract_image_url(element)
            product_info['이미지URL'] = image_url
            
            # 상품 링크와 코드 추출
            link_info = self._extract_link_info(element)
            product_info.update(link_info)
            
            # 기본 정보 설정
            product_info['검색키워드'] = keyword
            product_info['선택됨'] = False
            product_info['목표가격'] = ""
            product_info['크롤링시간'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 가격 히스토리 초기화
            current_date = datetime.now().strftime('%Y-%m-%d')
            product_info['가격히스토리'] = [{
                '날짜': current_date,
                '원가': product_info.get('원가', ''),
                '할인가': product_info.get('할인가', ''),
                '시간': datetime.now().strftime('%H:%M:%S')
            }]
            
            return product_info
            
        except Exception as e:
            return None
    
    def _extract_text_by_selectors(self, element, selectors):
        """여러 셀렉터로 텍스트 추출 시도"""
        for selector in selectors:
            try:
                elem = element.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 0:
                        return text
            except:
                continue
        return ""
    
    def _extract_price_info(self, element):
        """가격 정보 추출"""
        price_info = {'원가': '', '할인가': ''}
        
        try:
            # 가격 섹션 찾기
            price_section = None
            price_selectors = [
                ".prd_price", ".price", "[class*='price']", ".cost", ".amount",
                ".item_price", ".goods_price", ".prod_price"  # 모바일
            ]
            
            for selector in price_selectors:
                price_section = element.select_one(selector)
                if price_section:
                    break
            
            if not price_section:
                price_section = element  # 전체 요소에서 찾기
            
            # 원가 추출 (할인 전 가격)
            original_selectors = [
                ".tx_org .tx_num", ".original", ".before", "strike", "del",
                "[class*='original']", "[class*='before']", ".old_price",
                ".regular_price", ".list_price"
            ]
            
            for selector in original_selectors:
                elem = price_section.select_one(selector)
                if elem:
                    price_text = elem.get_text(strip=True)
                    clean_price = self._clean_price(price_text)
                    if clean_price:
                        price_info['원가'] = clean_price
                        break
            
            # 할인가 추출 (현재 가격)
            discount_selectors = [
                ".tx_cur .tx_num", ".current", ".sale", ".final", ".now",
                "[class*='current']", "[class*='sale']", "[class*='final']",
                ".sale_price", ".discount_price", ".special_price"
            ]
            
            for selector in discount_selectors:
                elem = price_section.select_one(selector)
                if elem:
                    price_text = elem.get_text(strip=True)
                    clean_price = self._clean_price(price_text)
                    if clean_price:
                        price_info['할인가'] = clean_price
                        break
            
            # 가격을 하나도 찾지 못한 경우, 숫자 패턴으로 찾기
            if not price_info['원가'] and not price_info['할인가']:
                all_text = price_section.get_text() if price_section else element.get_text()
                prices = re.findall(r'[\d,]+\s*원?', all_text)
                
                if prices:
                    # 첫 번째 가격을 할인가로 사용
                    clean_price = self._clean_price(prices[0])
                    if clean_price:
                        price_info['할인가'] = clean_price
                    
                    # 두 번째 가격이 있으면 원가로 사용
                    if len(prices) > 1:
                        clean_original = self._clean_price(prices[1])
                        if clean_original and int(clean_original.replace(',', '')) > int(clean_price.replace(',', '')):
                            price_info['원가'] = clean_original
            
            # 할인가만 있고 원가가 없는 경우
            if price_info['할인가'] and not price_info['원가']:
                price_info['원가'] = price_info['할인가']
            
        except Exception as e:
            pass
        
        return price_info
    
    def _clean_price(self, price_text):
        """가격 텍스트 정리"""
        if not price_text:
            return ""
        
        # 숫자와 쉼표만 추출
        numbers = re.findall(r'[\d,]+', price_text)
        if numbers:
            price_str = numbers[0].replace(',', '')
            if price_str.isdigit() and int(price_str) > 100:  # 100원 이상인 경우만
                return f"{int(price_str):,}"
        
        return ""
    
    def _extract_benefits(self, element):
        """혜택 정보 추출"""
        benefits = []
        
        benefit_selectors = [
            ".prd_flag .icon_flag", ".benefit", ".tag", "[class*='flag']", 
            "[class*='benefit']", ".event", ".promotion", ".special",
            # 모바일
            ".item_flag", ".goods_flag", ".prod_flag"
        ]
        
        for selector in benefit_selectors:
            benefit_elems = element.select(selector)
            for benefit_elem in benefit_elems:
                benefit_text = benefit_elem.get_text(strip=True)
                if benefit_text and benefit_text not in benefits:
                    benefits.append(benefit_text)
        
        return ", ".join(benefits)
    
    def _extract_image_url(self, element):
        """이미지 URL 추출"""
        img_selectors = [
            "img", ".prd_thumb img", ".thumb img", "[class*='img'] img",
            ".item_img img", ".goods_img img", ".prod_img img"  # 모바일
        ]
        
        for selector in img_selectors:
            img_elem = element.select_one(selector)
            if img_elem:
                image_url = img_elem.get('src', '') or img_elem.get('data-src', '')
                if image_url:
                    # 상대 경로를 절대 경로로 변환
                    if image_url.startswith('//'):
                        image_url = 'https:' + image_url
                    elif image_url.startswith('/'):
                        image_url = 'https://www.oliveyoung.co.kr' + image_url
                    return image_url
        
        return ""
    
    def _extract_link_info(self, element):
        """상품 링크와 코드 추출"""
        link_info = {'상품코드': '', '상품URL': ''}
        
        try:
            # 링크 요소 찾기
            link_elem = element.select_one("a")
            if not link_elem:
                link_elem = element.find_parent("a")
            
            if link_elem:
                href = link_elem.get('href', '')
                if href:
                    # 상품 코드 추출
                    goods_patterns = [
                        r'goodsNo=([A-Z0-9]+)',
                        r'goods_no=([A-Z0-9]+)',
                        r'prdNo=([A-Z0-9]+)',
                        r'/goods/([A-Z0-9]+)',
                        r'/product/([A-Z0-9]+)'
                    ]
                    
                    for pattern in goods_patterns:
                        match = re.search(pattern, href, re.I)
                        if match:
                            link_info['상품코드'] = match.group(1)
                            break
                    
                    # 상품 URL 구성
                    if href.startswith('http'):
                        link_info['상품URL'] = href
                    elif href.startswith('/'):
                        link_info['상품URL'] = 'https://www.oliveyoung.co.kr' + href
                    else:
                        link_info['상품URL'] = 'https://www.oliveyoung.co.kr/' + href
            
            # 데이터 속성에서도 시도
            if not link_info['상품코드']:
                for attr in ['data-goodsno', 'data-goods-no', 'data-prd-no', 'data-product-id']:
                    value = element.get(attr)
                    if value:
                        link_info['상품코드'] = value
                        break
        
        except Exception as e:
            pass
        
        return link_info

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
    st.title("🛍️ 올리브영 상품 크롤러 (Requests 버전)")
    
    # 앱 소개
    st.markdown("""
    ### 🎯 **주요 기능**
    - **실시간 상품 검색**: 올리브영에서 원하는 상품을 검색하고 가격 정보를 수집합니다
    - **관심 상품 관리**: 원하는 상품을 관심 목록에 추가하고 목표 가격을 설정할 수 있습니다
    - **가격 추적**: 관심 상품의 가격 변화를 추적하고 그래프로 확인할 수 있습니다
    - **엑셀 내보내기**: 상품 정보와 가격 히스토리를 엑셀 파일로 저장할 수 있습니다
    
    ### 🎭 **데이터 모드 안내**
    - **실제 크롤링**: 올리브영 웹사이트에서 실시간 데이터를 수집 (차단될 수 있음)
    - **모의 데이터**: 실제와 유사한 가상의 상품 데이터로 앱 기능 테스트
    - **자동 모드**: 실제 크롤링 실패 시 자동으로 모의 데이터 생성 ⭐**권장**
    """)
    
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
                debug_info = st.empty()
                
                def update_progress(message, progress=None):
                    status_text.text(message)
                    if progress is not None:
                        progress_bar.progress(progress)
                    debug_info.info(f"🔍 {message}")
                
                # 크롤링 실행
                with st.spinner("크롤링 중..."):
                    try:
                        st.info(f"🎯 검색 키워드: {', '.join(keywords)}")
                        st.info(f"📄 페이지 수: {max_pages} | 🌐 다중 URL 방식 사용")
                        
                        # 실제 크롤링 시도
                        products = st.session_state.scraper.scrape_products(
                            keywords, 
                            max_pages,
                            progress_callback=update_progress
                        )
                        
                        st.session_state.products_data = products
                        save_data()
                        
                        progress_bar.progress(1.0)
                        status_text.text(f"✅ 완료! 총 {len(products)}개 상품")
                        
                        if len(products) > 0:
                            st.success(f"🎉 {len(products)}개 상품을 찾았습니다!")
                            
                            # 샘플 상품 정보 표시
                            st.subheader("📋 상품 샘플")
                            sample_count = min(5, len(products))
                            for i in range(sample_count):
                                product = products[i]
                                brand = product.get('브랜드', 'N/A')
                                name = product.get('상품명', 'N/A')[:50]
                                price = product.get('할인가', product.get('원가', 'N/A'))
                                keyword = product.get('검색키워드', 'N/A')
                                st.info(f"**{brand}** - {name}... | 가격: {price}원 | 키워드: {keyword}")
                        else:
                            st.warning("⚠️ 상품을 찾을 수 없습니다.")
                            st.info("🔧 **해결 방법:**")
                            st.info("1. 다른 검색어를 시도해보세요 (예: 토너, 세럼, 클렌징)")
                            st.info("2. 5분 후 다시 시도해보세요")
                            st.info("3. 페이지 수를 1로 줄여보세요")
                            st.info("4. 아래 테스트 기능으로 연결 상태를 확인해보세요")
                        
                        debug_info.empty()
                        
                    except Exception as e:
                        st.error(f"❌ 크롤링 오류: {str(e)}")
                        st.info("🔧 **문제 해결:**")
                        st.info("1. 인터넷 연결을 확인해주세요")
                        st.info("2. 잠시 후 다시 시도해주세요")
                        st.info("3. 아래 연결 테스트를 실행해보세요")
                        
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
        
        # 디버그 섹션
        st.markdown("---")
        st.subheader("🔧 테스트")
        
        col_test1, col_test2 = st.columns(2)
        
        with col_test1:
            if st.button("🧪 연결 테스트", use_container_width=True):
                try:
                    test_url = "https://www.oliveyoung.co.kr"
                    response = requests.get(test_url, timeout=10)
                    if response.status_code == 200:
                        st.success(f"✅ 올리브영 연결 성공 ({response.status_code})")
                    else:
                        st.warning(f"⚠️ 응답 코드: {response.status_code}")
                except Exception as e:
                    st.error(f"❌ 연결 실패: {str(e)}")
        
        with col_test2:
            if st.button("🎭 모의 데이터 테스트", use_container_width=True):
                try:
                    test_products = generate_mock_data(["테스트"], 3)
                    st.success(f"✅ 모의 데이터 {len(test_products)}개 생성 성공")
                    if test_products:
                        st.json(test_products[0])  # 첫 번째 상품 정보 표시
                except Exception as e:
                    st.error(f"❌ 모의 데이터 생성 실패: {str(e)}")
        
        if st.button("🔍 실제 크롤링 테스트", use_container_width=True):
            test_keyword = "토너"
            progress_text = st.empty()
            
            def test_progress(msg, prog=None):
                progress_text.text(msg)
            
            try:
                scraper = OliveYoungScraper()
                results = scraper.scrape_products([test_keyword], 1, test_progress)
                if len(results) > 0:
                    st.success(f"✅ 실제 크롤링 성공: {len(results)}개 상품 발견")
                    st.json(results[0])  # 첫 번째 상품 정보 표시
                else:
                    st.warning("⚠️ 실제 크롤링에서 상품을 찾지 못했습니다")
                    st.info("올리브영이 크롤링을 차단하고 있을 가능성이 높습니다. 모의 데이터를 사용하세요.")
            except Exception as e:
                st.error(f"❌ 크롤링 테스트 실패: {str(e)}")
                st.info("💡 해결책: '자동 (크롤링 실패 시 모의 데이터)' 모드를 사용하세요")
            finally:
                progress_text.empty()
    
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
                            if not image_url.startswith('http'):
                                image_url = 'https:' + image_url if image_url.startswith('//') else 'https://www.oliveyoung.co.kr' + image_url
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
                                updated_products = st.session_state.scraper.scrape_selected_products(
                                    selected_products,
                                    progress_callback=update_progress
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
                            if not image_url.startswith('http'):
                                image_url = 'https:' + image_url if image_url.startswith('//') else 'https://www.oliveyoung.co.kr' + image_url
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
            
            # 관심상품 기능 안내
            st.markdown("""
            ### 📚 **관심상품 기능 안내**
            
            #### 🛍️ **상품 추가 방법**
            1. **검색 결과 탭**에서 원하는 상품의 **⭐ 관심상품 추가** 버튼 클릭
            2. 또는 **⭐ 전체 관심상품 추가** 버튼으로 모든 검색 결과를 한 번에 추가
            
            #### 🎯 **목표가격 설정**
            - 관심상품에 목표가격을 설정하면 가격이 목표치 이하로 떨어졌을 때 확인 가능
            - 목표가격 달성 여부를 한눈에 확인하고 할인 금액까지 계산
            
            #### 🔄 **가격 추적**
            - **🔄 선택된 상품 새로고침**으로 최신 가격 정보 업데이트
            - 가격 변화 히스토리를 그래프와 표로 확인
            
            #### 📊 **데이터 내보내기**
            - **전체 엑셀 다운로드**: 모든 관심상품 정보
            - **선택된 상품 다운로드**: 체크한 상품만 선별 다운로드
            - 가격 히스토리, 목표가격 달성 상품 등 별도 시트로 구성
            
            ### 🎭 **모의 데이터로 기능 테스트**
            실제 상품이 없어도 모의 데이터로 모든 기능을 체험해보세요!
            """)
            
            # 기능 미리보기
            st.subheader("⚡ 기능 미리보기")
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**목표가격 달성 알림**")
                st.success("✅ 라네즈 토너 - 목표가격 15,000원 달성! (현재 14,500원)")
                st.warning("❌ 헤라 세럼 - 목표가격 미달성 (현재 32,000원, 목표 30,000원)")
            
            with col2:
                st.markdown("**가격 변화 추적**")
                st.info("📈 이니스프리 선크림: 15,000원 → 13,500원 → 12,000원 (20% 할인)")
                st.info("📊 총 3회 가격 변동 기록됨")

# 자동 데이터 로드
if __name__ == "__main__":
    init_session_state()
    load_data()
    main()
