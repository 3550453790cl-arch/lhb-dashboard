import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import time
from openai import OpenAI

# 设置页面配置（必须是第一个 Streamlit 命令）
st.set_page_config(
    page_title="龙虎榜分析看板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 辅助函数：格式化大数字
def format_number(num):
    if pd.isna(num):
        return "0"
    num = float(num)
    if num >= 100000000:
        return f"{num / 100000000:.2f}亿"
    elif num >= 10000:
        return f"{num / 10000:.2f}万"
    else:
        return f"{num:.2f}"

# 核心数据获取函数（带缓存）
@st.cache_data(ttl=3600)  # 缓存1小时
def get_lhb_data(date_str):
    """
    获取指定日期的龙虎榜数据
    返回: (detail_df, jg_df, yyb_df)
    """
    try:
        # 1. 龙虎榜详情
        detail_df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
        if detail_df is None or detail_df.empty:
            return None, None, None
            
        # 2. 机构数据
        jg_df = ak.stock_lhb_jgmmtj_em(start_date=date_str, end_date=date_str)
        
        # 3. 营业部数据（用于计算外资）
        yyb_df = ak.stock_lhb_hyyyb_em(start_date=date_str, end_date=date_str)
        
        return detail_df, jg_df, yyb_df
    except Exception as e:
        st.error(f"获取数据时出错: {e}")
        return None, None, None

# 智能日期回溯
def find_latest_data():
    today = datetime.now()
    # 尝试回溯最近 10 天
    for i in range(10):
        check_date = today - timedelta(days=i)
        date_str = check_date.strftime("%Y%m%d")
        display_date = check_date.strftime("%Y-%m-%d")
        week_day = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][check_date.weekday()]
        
        # 尝试获取详情数据来判断是否有数据
        try:
            # 这里不使用缓存的函数，因为要快速探测
            # 但为了避免频繁请求被封，我们可以直接调用 get_lhb_data，因为如果失败它返回 None
            # 不过 get_lhb_data 会调用三个接口，有点重。
            # 我们先只调一个轻量的
            df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
            if df is not None and not df.empty:
                return date_str, f"{display_date}（{week_day}）"
        except:
            pass
    
    return None, None

# 主程序
def main():
    st.title("📈 东方财富龙虎榜分析看板")
    
    # 1. 智能获取日期
    with st.spinner("正在寻找最近的交易日数据..."):
        date_str, date_display = find_latest_data()
    
    if not date_str:
        st.error("最近10天没有找到龙虎榜数据，请检查网络或稍后再试。")
        return

    st.success(f"当前展示数据日期：**{date_display}**")
    
    # 2. 获取详细数据
    with st.spinner(f"正在抓取 {date_display} 的详细数据..."):
        detail_df, jg_df, yyb_df = get_lhb_data(date_str)
    
    if detail_df is None:
        st.error("无法获取详细数据。")
        return

    # 3. 计算关键指标
    # (1) 上榜个股总数
    total_stocks = len(detail_df['代码'].unique())
    
    # (2) 机构买入总额
    jg_buy_total = 0
    if jg_df is not None and not jg_df.empty:
        jg_buy_total = jg_df['机构买入总额'].sum()
        
    # (3) 外资买入总额 (筛选深股通/沪股通)
    waizi_buy_total = 0
    if yyb_df is not None and not yyb_df.empty:
        waizi_mask = yyb_df['营业部名称'].str.contains('股通')
        waizi_buy_total = yyb_df[waizi_mask]['买入总金额'].sum()

    # 4. 展示关键指标
    st.subheader("📊 市场概览")
    col1, col2, col3 = st.columns(3)
    col1.metric("上榜个股", f"{total_stocks} 只")
    col2.metric("机构买入", format_number(jg_buy_total))
    col3.metric("外资买入", format_number(waizi_buy_total))
    
    st.markdown("---")
    
    # 5. 榜一大哥
    st.subheader("👑 榜一大哥")
    
    # 按净买额排序
    # 注意：'龙虎榜净买额' 可能是字符串或数字，需要处理
    # AkShare 返回的通常已经是数字，或者是 float64
    # 确保是数字
    if '龙虎榜净买额' in detail_df.columns:
        detail_df['龙虎榜净买额'] = pd.to_numeric(detail_df['龙虎榜净买额'], errors='coerce')
        
    top1_stock = detail_df.sort_values(by='龙虎榜净买额', ascending=False).iloc[0]
    
    top1_name = top1_stock['名称']
    top1_code = top1_stock['代码']
    top1_net_buy = top1_stock['龙虎榜净买额']
    top1_change = top1_stock['涨跌幅']
    top1_reason = top1_stock['上榜原因']
    
    st.info(
        f"**{top1_name}** ({top1_code})\n\n"
        f"💰 净买入：**{format_number(top1_net_buy)}**\n\n"
        f"📈 涨跌幅：{top1_change}%\n\n"
        f"📝 上榜原因：{top1_reason}"
    )
    
    st.markdown("---")
    
    # 6. 榜单明细
    st.subheader("📋 净买入 TOP 10")
    
    # 筛选列并排序
    display_cols = ['名称', '代码', '收盘价', '涨跌幅', '龙虎榜净买额']
    # 确保列存在
    actual_cols = [c for c in display_cols if c in detail_df.columns]
    
    top10_df = detail_df.sort_values(by='龙虎榜净买额', ascending=False).head(10)[actual_cols]
    
    # 格式化显示
    # 为了手机端好看，可以将净买额格式化
    top10_show = top10_df.copy()
    top10_show['龙虎榜净买额'] = top10_show['龙虎榜净买额'].apply(format_number)
    
    # 使用 dataframe 展示
    st.dataframe(
        top10_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "名称": st.column_config.TextColumn("名称", width="medium"),
            "代码": st.column_config.TextColumn("代码", width="small"),
            "收盘价": st.column_config.NumberColumn("收盘价", format="%.2f"),
            "涨跌幅": st.column_config.NumberColumn("涨幅", format="%.2f%%"),
            "龙虎榜净买额": st.column_config.TextColumn("净买入", width="medium"),
        }
    )
    
    # 底部提示
    st.caption("数据来源：东方财富网 | 数据更新可能有延迟")

    # --- AI 深度分析功能 ---
    st.markdown("---")
    st.subheader("🤖 AI 深度分析")

    if st.button("开始 AI 分析", type="primary"):
        # 1. 检查密钥配置
        secrets_missing = False
        try:
            if "openai" not in st.secrets:
                secrets_missing = True
        except Exception:
            secrets_missing = True

        if secrets_missing:
            st.error("请先配置 OpenAI 密钥！请在项目根目录下创建 .streamlit/secrets.toml 文件。")
            st.info("""
            **配置示例 (.streamlit/secrets.toml):**
            ```toml
            [openai]
            api_key = "sk-..."
            base_url = "https://api.openai.com/v1"  # 或其他兼容的 Base URL
            ```
            """)
            return

        # 2. 准备数据给 AI
        # 选取 AI 需要的列
        ai_cols = ['名称', '代码', '龙虎榜净买额', '涨跌幅', '换手率']
        # 确保列都存在 (换手率可能在某些特定情况下没有，做个容错)
        existing_ai_cols = [c for c in ai_cols if c in detail_df.columns]
        
        ai_df = detail_df.sort_values(by='龙虎榜净买额', ascending=False).head(10)[existing_ai_cols]
        
        # 重命名列以节省 Token 并让 AI 更易读
        ai_df = ai_df.rename(columns={
            '名称': '股票名', 
            '龙虎榜净买额': '净买入',
            '涨跌幅': '涨幅'
        })
        
        # 转换为 Markdown 字符串
        data_str = ai_df.to_markdown(index=False)

        # 3. 构建 Prompt
        system_prompt = """
        你是一位拥有 20 年经验的 A 股资深游资分析师。
        请根据提供的龙虎榜净买入前 10 名数据，对每只上榜股票进行简短点评，并在最后给出市场总结。
        
        要求：
        1. 逐个点评：对每一只股票，用一句话点评其资金性质（机构/游资/散户）、板块地位或技术形态。
        2. 市场总结：在点评完所有股票后，总结今日市场情绪（情绪高潮/分歧/退潮）和主线热点。
        3. 风格犀利、简练、不要说废话。
        4. 使用 Markdown 格式输出。
        """

        user_prompt = f"""
        这是今日龙虎榜净买入前 10 名的数据：
        {data_str}
        
        请开始你的分析：
        """

        # 4. 调用 AI
        try:
            client = OpenAI(
                api_key=st.secrets["openai"]["api_key"],
                base_url=st.secrets["openai"]["base_url"]
            )
            
            with st.spinner('AI 正在分析龙虎榜数据，请稍候...'):
                # 尝试从 secrets 获取模型名称，默认为 gpt-3.5-turbo
                model_name = st.secrets["openai"].get("model", "gpt-3.5-turbo")
                
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7
                )
                
                analysis_result = response.choices[0].message.content
                
            st.success("分析完成！")
            st.markdown("### 🧠 资深游资点评")
            st.info(analysis_result)
            
        except Exception as e:
            st.error(f"AI 分析请求失败: {e}")


if __name__ == "__main__":
    main()
