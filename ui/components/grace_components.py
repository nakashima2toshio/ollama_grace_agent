
import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Dict, Any, Optional
from grace.schemas import ExecutionPlan

def display_confidence_metric(score: float, level: str, breakdown: Dict[str, float]):
    """信頼度スコアと内訳を表示するコンポーネント"""
    
    # スコア表示
    color = "green" if score >= 0.7 else "orange" if score >= 0.4 else "red"
    st.metric(
        label="Current Confidence",
        value=f"{score:.2f}",
        delta=level,
        delta_color="normal" if score >= 0.7 else "inverse"
    )
    st.progress(score)
    
    # 内訳チャート（レーダーチャート風）
    if breakdown:
        df = pd.DataFrame({
            "Factor": list(breakdown.keys()),
            "Score": list(breakdown.values())
        })
        fig = px.bar(
            df, 
            x="Score", 
            y="Factor", 
            orientation='h', 
            range_x=[0, 1],
            title="Confidence Breakdown",
            height=200
        )
        fig.update_layout(margin=dict(l=0, r=0, t=30, b=0))
        # st.plotly_chart(fig, use_container_width=True)
        st.plotly_chart(fig, use_container_width=True)

def display_execution_plan(plan: ExecutionPlan, current_step_id: int = 0):
    """実行計画の進捗を表示"""
    st.subheader("📋 Execution Plan")
    st.caption(f"Query: {plan.original_query}")
    
    for step in plan.steps:
        status_icon = "⏳"
        status_color = "gray"
        
        if step.step_id < current_step_id:
            status_icon = "✅"
            status_color = "green"
        elif step.step_id == current_step_id:
            status_icon = "▶️"
            status_color = "blue"
            
        st.markdown(
            f"""
            <div style="padding: 10px; border-radius: 5px; border: 1px solid #ddd; margin-bottom: 5px; background-color: {status_color}10;">
                <strong>{status_icon} Step {step.step_id}: {step.action}</strong><br>
                <span style="font-size: 0.9em;">{step.description}</span><br>
                <code style="font-size: 0.8em; color: #666;">Query: {step.query}</code>
            </div>
            """,
            unsafe_allow_html=True
        )

def display_intervention_request(request: Dict[str, Any], on_response: callable):
    """介入リクエスト（確認・入力）を表示"""
    req_type = request.get("type")
    data = request.get("data", {})
    
    with st.container():
        st.warning(f"⚠️ Intervention Required: {req_type.upper()}")
        
        if req_type == "confirm":
            st.write(data.get("message", "Confirm action?"))
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Proceed", key="btn_proceed"):
                    on_response("proceed")
            with col2:
                if st.button("🛑 Stop", key="btn_stop"):
                    on_response("stop")
                    
        elif req_type == "escalate":
            st.write(data.get("message", "More info needed."))
            user_input = st.text_input("Your Answer:", key="input_escalate")
            if st.button("Submit", key="btn_submit_escalate"):
                on_response(user_input)
