"""CSS used by the PiCare Streamlit mock application."""

APP_CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');

:root {
  --picare-red: #ed003f;
  --picare-red-dark: #c90036;
  --picare-pink: #fff0f3;
  --picare-ink: #101820;
  --picare-muted: #677180;
  --picare-line: #dde2e8;
  --picare-green: #14822b;
}

html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.stApp { background: #ffffff; color: var(--picare-ink); }
.block-container { max-width: 1440px; padding: 0 2.8rem 4rem; }
[data-testid="stHeader"] { display: none; }
[data-testid="stToolbar"] { display: none; }
#MainMenu, footer { visibility: hidden; }

.picare-brand { font-size: 1.75rem; font-weight: 800; color: var(--picare-red); letter-spacing: -.03em; padding: .8rem 0 .5rem; }
.picare-brand span { font-size: 1.7rem; margin-right: .45rem; }
.picare-doc-badge { width: fit-content; margin: .6rem 0 .35rem auto; border: 1px solid var(--picare-red); color: var(--picare-red); border-radius: 10px; padding: .55rem .9rem; font-weight: 700; }
.picare-header-line { border-bottom: 1px solid var(--picare-line); margin: 0 -2.8rem 1.5rem; }
[data-testid="stRadio"] > div { justify-content: center; gap: 1.7rem; flex-wrap: nowrap; }
[data-testid="stRadio"] label { font-weight: 700; white-space: nowrap; }
[data-testid="stRadio"] label:has(input:checked) { color: var(--picare-red); }
[data-testid="stRadio"] label:has(input:checked) p { color: var(--picare-red); }

.hero { text-align: center; padding: .3rem 0 1.3rem; }
.hero h1 { font-size: clamp(2rem, 4vw, 3.1rem); margin: 0; letter-spacing: -.045em; }
.hero h1 em { color: var(--picare-red); font-style: normal; }
.hero p { color: var(--picare-muted); font-size: 1.05rem; margin: .45rem 0 0; }
.mock-ribbon { width: fit-content; margin: .2rem auto .8rem; color: #8b4b00; background: #fff7e6; border: 1px solid #ffd899; border-radius: 999px; padding: .28rem .7rem; font-size: .78rem; font-weight: 700; }

[data-testid="stForm"] { border: 1px solid var(--picare-line); border-radius: 14px; padding: 1.1rem 1.4rem 1.2rem; box-shadow: 0 3px 14px rgba(22, 31, 40, .035); }
[data-testid="stForm"] [data-testid="stWidgetLabel"] p { font-weight: 700; color: var(--picare-ink); }
.stButton > button, .stFormSubmitButton > button { border-radius: 9px; min-height: 42px; font-weight: 700; }
.stFormSubmitButton > button { background: linear-gradient(135deg, var(--picare-red), #d9003b); border-color: var(--picare-red); color: white; }
.stFormSubmitButton > button:hover { background: var(--picare-red-dark); color: white; border-color: var(--picare-red-dark); }

.section-title { display: flex; align-items: center; gap: .65rem; margin: 1.3rem 0 .75rem; }
.section-title h2 { font-size: 1.35rem; margin: 0; }
.status-pill { background: #e9f8ed; color: var(--picare-green); border-radius: 999px; padding: .25rem .65rem; font-size: .78rem; font-weight: 700; }

.product-card { border: 1px solid var(--picare-line); border-radius: 13px; padding: .9rem 1rem 1rem; min-height: 405px; box-shadow: 0 2px 12px rgba(22,31,40,.035); }
.product-badge { display: inline-block; padding: .25rem .55rem; border-radius: 7px; font-size: .76rem; font-weight: 700; margin-bottom: .55rem; }
.tone-primary { color: white; background: var(--picare-red); }
.tone-warm { color: #c25b05; background: #fff1e5; border: 1px solid #ffd3ad; }
.tone-green { color: var(--picare-green); background: #eaf7ec; border: 1px solid #cbe9d0; }
.product-name { font-weight: 800; font-size: 1.06rem; margin: .25rem 0 .5rem; }
.spec-grid { display: grid; grid-template-columns: 4.2rem 1fr; gap: .35rem .5rem; font-size: .82rem; margin-top: .55rem; }
.spec-grid strong { color: #333c47; }
.product-reason { margin-top: .8rem; padding: .42rem .55rem; border-radius: 7px; background: var(--picare-pink); color: var(--picare-red-dark); font-size: .78rem; font-weight: 700; text-align: center; }

.source-card { border: 1px solid var(--picare-line); border-radius: 12px; padding: .85rem 1rem; margin-bottom: .55rem; display: flex; align-items: center; gap: .8rem; }
.source-icon { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; background: #ffe9ee; color: var(--picare-red); font-size: 1.1rem; flex: 0 0 auto; }
.source-title { font-weight: 700; font-size: .9rem; }
.source-meta { color: var(--picare-muted); font-size: .77rem; margin-top: .15rem; }
.source-link { margin-left: auto; color: var(--picare-red); text-decoration: none; font-weight: 800; font-size: 1.1rem; }

.qa-category { border: 1px solid var(--picare-line); border-radius: 12px; padding: 1rem; text-align: center; font-weight: 700; background: white; }
.user-bubble { width: fit-content; max-width: 75%; margin: .9rem 0 .9rem auto; background: #ffe7eb; border-radius: 18px 18px 3px 18px; padding: .8rem 1.15rem; font-weight: 500; }
.answer-card { border: 1px solid var(--picare-line); border-radius: 14px; padding: 1.2rem 1.3rem; box-shadow: 0 3px 15px rgba(22,31,40,.05); }
.answer-label { color: var(--picare-green); font-size: .88rem; font-weight: 800; margin-bottom: .8rem; }
.answer-label.blocked { color: #b15b00; }
.answer-card h3 { margin: 0 0 .45rem; font-size: 1.2rem; }
.answer-card p { line-height: 1.72; color: #303945; }
.step-row { display: grid; grid-template-columns: 2rem 1fr; gap: .7rem; align-items: center; border: 1px solid var(--picare-line); border-radius: 9px; padding: .65rem .75rem; margin: .4rem 0; }
.step-number { display: grid; place-items: center; width: 1.75rem; height: 1.75rem; border-radius: 50%; background: var(--picare-red); color: white; font-weight: 800; font-size: .82rem; }
.warning-box { margin-top: .7rem; border: 1px solid #f2d59d; background: #fff8e8; color: #a55d00; border-radius: 8px; padding: .65rem .8rem; font-size: .84rem; }
.related-card { border: 1px solid var(--picare-line); border-radius: 9px; padding: .7rem .8rem; margin-bottom: .45rem; color: #37414d; background: #fff; }

[data-testid="stJson"] { border: 1px solid var(--picare-line); border-radius: 10px; }
[data-testid="stDataFrame"] { border: 1px solid var(--picare-line); border-radius: 11px; overflow: hidden; }
[data-testid="stChatInput"] { max-width: 1380px; margin: 0 auto; }

@media (max-width: 760px) {
  .block-container { padding: 0 1rem 5rem; }
  .picare-header-line { margin: 0 -1rem 1rem; }
  [data-testid="stRadio"] > div { gap: .5rem; }
  [data-testid="stRadio"] label { font-size: .72rem; }
  .picare-doc-badge { font-size: .75rem; }
  .product-card { min-height: auto; }
  .user-bubble { max-width: 94%; }
}
</style>
"""
