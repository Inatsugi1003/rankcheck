import json
import pandas as pd
import streamlit as st
from urllib.parse import urlparse
import time
import requests

st.set_page_config(page_title="JP Rank Checker", page_icon="🔎", layout="centered")
st.title("🔎 日本向けシンプル ランクチェッカー")

st.caption("国は常に JP（日本）。都市は未指定でも可。Googleの上位結果内で特定ドメインが何位かを確認します。")
st.info("Secretsに SERPAPI_KEY を設定してください。Streamlit Cloud > App > Settings > Secrets")

API_URL = "https://serpapi.com/search.json"

def _domain_of(s: str) -> str:
    if not s: return ""
    if "://" in s:
        return urlparse(s).netloc.lower().lstrip(".")
    return s.lower().lstrip(".")

def fetch_serp(keyword: str, api_key: str, city: str|None, device: str, num: int):
    if not api_key:
        raise RuntimeError("SERPAPI_KEY が未設定です。Secretsに追加してください。")
    params = {
        "engine": "google",
        "q": keyword,
        "gl": "JP",      # 日本固定
        "hl": "ja",
        "device": device,
        "num": num,
        "api_key": api_key
    }
    if city:
        params["location"] = city
    # リトライ
    last_status = None
    last_text = ""
    for attempt in range(5):
        r = requests.get(API_URL, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        last_status = r.status_code
        last_text = r.text[:300]
        if r.status_code in (429, 500, 502, 503):
            time.sleep(1.5 * (attempt + 1))
            continue
        r.raise_for_status()
    raise RuntimeError(f"SERP取得失敗 status={last_status} body={last_text}")

def parse_rank(serp_json: dict, target_domain: str, top_k: int = 10):
    organic = (serp_json.get("organic_results") or [])[:top_k]
    rank, matched_url = None, ""
    for i, item in enumerate(organic, start=1):
        link = item.get("link") or item.get("url") or ""
        if target_domain and target_domain in link:
            rank, matched_url = i, link
            break
    features = {
        "featured_snippet": bool(serp_json.get("answer_box")),
        "paa": bool(serp_json.get("related_questions")),
        "video": any(("video" in str(item)) for item in organic),
        "local_pack": bool(serp_json.get("local_results")),
    }
    top = [{"rank": i, "title": item.get("title"), "url": item.get("link") or item.get("url")}
           for i, item in enumerate(organic, start=1)]
    return rank, matched_url, features, top

with st.form("single"):
    kw = st.text_input("キーワード", placeholder="例）ランクトラッカー")
    target = st.text_input("対象ドメイン / URL", placeholder="例）example.com または https://example.com")
    col1, col2 = st.columns(2)
    with col1:
        device = st.selectbox("デバイス", ["desktop", "mobile"], index=0)
    with col2:
        city = st.text_input("都市（任意）", placeholder="例）Tokyo / Osaka（空欄OK）")
    topk = st.slider("上位何位まで取得", min_value=10, max_value=100, value=10, step=10)
    submitted = st.form_submit_button("チェックする")

if submitted:
    try:
        api_key = st.secrets.get("SERPAPI_KEY")
        serp = fetch_serp(kw, api_key=api_key, city=(city or None), device=device, num=topk)
        rank, url, feats, top = parse_rank(serp, _domain_of(target), top_k=topk)

        st.subheader("結果")
        st.write(f"**キーワード**：{kw}")
        st.write(f"**対象**：{_domain_of(target)}")
        if rank is None:
            st.error(f"上位{topk}位に対象ドメインは見つかりませんでした（圏外）。")
        else:
            st.success(f"✅ 順位：**{rank} 位**")
            st.write(f"一致URL：{url}")

        with st.expander("SERP特徴"):
            st.json(feats)

        df = pd.DataFrame(top, columns=["rank", "title", "url"])
        st.dataframe(df, use_container_width=True)
        st.download_button("上位結果をCSVでダウンロード", df.to_csv(index=False), "top_results.csv", "text/csv")

    except Exception as e:
        st.exception(e)
