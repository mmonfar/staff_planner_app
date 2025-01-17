import streamlit as st
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.planner import StaffPlanner
import pandas as pd
import matplotlib.pyplot as plt

# Set App on Wide Mode
st.set_page_config(layout="wide", page_title="Staff Planner App", page_icon="📊")

# App title
st.title("📊 Staff Planner App")
st.subheader("Compare Workforce Planning Models (Model A & Model B)")

# Sidebar: Inputs
st.sidebar.header("Modify Parameters")

# Unit census and vacation days (with an expander)
with st.sidebar.expander("Units Census and Vacation Days", expanded=True):
    unit_census = st.number_input("Unit Census", min_value=1, value=32, step=1)
    vacation_days = st.number_input("Vacation Days", min_value=0, value=30, step=1)

# Costs per discipline (with an expander)
with st.sidebar.expander("Costs per Discipline", expanded=True):
    sn_cost = st.number_input("Staff Nurse Cost", min_value=0.0, value=1.0, step=0.1)
    pn_cost = st.number_input("Practical Nurse Cost", min_value=0.0, value=0.65, step=0.1)
    hca_cost = st.number_input("Healthcare Assistant Cost", min_value=0.0, value=0.4, step=0.1)

# Ratios and overtime for Model A (with an expander)
with st.sidebar.expander("Model A Parameters", expanded=True):
    sn_a_ratio = st.number_input("SN Ratio (Model A)", min_value=1, value=8, step=1)
    pn_a_ratio = st.number_input("PN Ratio (Model A)", min_value=1, value=12, step=1)
    hca_a_ratio = st.number_input("HCA Ratio (Model A)", min_value=1, value=16, step=1)

    overtime_early = st.number_input("Early Shift SN Overtime per Week (Model A)", min_value=0, value=1, step=1)
    overtime_late = st.number_input("Late Shift SN Overtime per Week (Model A)", min_value=0, value=1, step=1)
    overtime_night = st.number_input("Night SN Overtime per Week (Model A)", min_value=0, value=1, step=1)

# Parameters for Model B (with an expander)
with st.sidebar.expander("Model B Parameters", expanded=True):
    sn_b_ratio = st.number_input("SN Ratio (Model B)", min_value=1, value=3, step=1)
    hca_b_ratio = st.number_input("HCA Ratio (Model B)", min_value=1, value=16, step=1)
    overtime_per_week_b = st.number_input("SN Overtime per Week (Model B)", min_value=0, value=5, step=1)

# Costs and ratios as dictionaries for StaffPlanner
costs = {'sn': sn_cost, 'pn': pn_cost, 'hca': hca_cost}
ratios = {'sn_a': sn_a_ratio, 'pn_a': pn_a_ratio, 'hca_a': hca_a_ratio, 'sn_b': sn_b_ratio, 'hca_b': hca_b_ratio}

# Create a planner instance
planner = StaffPlanner(unit_census=unit_census, vacation_days=vacation_days)

# Model Calculations
overtime_config_a = {'early': overtime_early, 'late': overtime_late, 'night': overtime_night}
model_a = planner.calculate_model_a(
    ratios={'sn': sn_a_ratio, 'pn': pn_a_ratio, 'hca': hca_a_ratio},
    overtime_config=overtime_config_a
)

model_b = planner.calculate_model_b(
    ratios={'sn': sn_b_ratio, 'hca': hca_b_ratio},
    overtime_per_week=overtime_per_week_b
)

# Main Screen: Results Table
st.subheader("Model Results Comparison")
comparison_df = pd.DataFrame({
    "Model": ["Model A", "Model B"],
    "Total Cost": [model_a['total_cost'], model_b['total_cost']],
    "SN Needs": [model_a['needs'].get('sn', 0), model_b['needs'].get('sn', 0)],
    "PN Needs": [model_a['needs'].get('pn', 0), 0],  # Model B has no PN
    "HCA Needs": [model_a['needs'].get('hca', 0), model_b['needs'].get('hca', 0)],
})
st.dataframe(comparison_df, use_container_width=True)

# Create two columns for side-by-side plots
col1, col2 = st.columns(2)

# Plot: Breakeven Analysis in the first column with custom size
with col1:
    st.subheader("Breakeven Analysis")
    
    unit_census_values = list(range(10, 48, 5))
    model_a_costs, model_b_costs = [], []

    for uc in unit_census_values:
        # Pass custom sidebar inputs for each unit_census
        temp_planner = StaffPlanner(
            unit_census=uc,
            vacation_days=vacation_days
        )
        temp_planner.costs = costs  # Apply sidebar costs

        # Calculate Model A with custom ratios and overtime
        model_a_costs.append(temp_planner.calculate_model_a(
            ratios={'sn': sn_a_ratio, 'pn': pn_a_ratio, 'hca': hca_a_ratio},
            overtime_config=overtime_config_a
        )['total_cost'])

        # Calculate Model B with custom ratios and overtime
        model_b_costs.append(temp_planner.calculate_model_b(
            ratios={'sn': sn_b_ratio, 'hca': hca_b_ratio},
            overtime_per_week=overtime_per_week_b
        )['total_cost'])  

    fig2, ax2 = plt.subplots(figsize=(6, 4))  # Adjust the width and height as desired
    
    # Plot lines with smaller markers
    ax2.plot(unit_census_values, model_a_costs, label="Model A", color="#494645", marker="o", markersize=4)  # smaller marker size
    ax2.plot(unit_census_values, model_b_costs, label="Model B", color="teal", marker="s", markersize=4)  # smaller marker size
    
    ax2.set_xlabel("Unit Census", fontsize=8)
    ax2.set_ylabel("Total Cost", fontsize=8)
    ax2.set_title("Breakeven Analysis: Cost vs Unit Census", fontsize=10)
    ax2.legend()

    # Add alternating data labels with more space between them
    for i, (x, y) in enumerate(zip(unit_census_values, model_a_costs)):
        if i % 2 == 0:
            ax2.text(x, y + 0.5, f"{y:.2f}", color="#494645", ha="center", va="bottom", fontsize=6)  # Adjust vertical space
        else:
            ax2.text(x, y - 0.5, f"{y:.2f}", color="#494645", ha="center", va="top", fontsize=6)  # Adjust vertical space
    
    for i, (x, y) in enumerate(zip(unit_census_values, model_b_costs)):
        if i % 2 == 0:
            ax2.text(x, y + 0.5, f"{y:.2f}", color="teal", ha="center", va="bottom", fontsize=6)  # Adjust vertical space
        else:
            ax2.text(x, y - 0.5, f"{y:.2f}", color="teal", ha="center", va="top", fontsize=6)  # Adjust vertical space

    st.pyplot(fig2)

# Plot: Total Costs in the second column with custom size
with col2:
    st.subheader("Model Cost Comparison")
    
    fig, ax = plt.subplots(figsize=(6, 4))  # Adjust the width and height as desired
    
    # Horizontal bar chart for total costs
    bars = ax.barh(["Model A", "Model B"], [model_a['total_cost'], model_b['total_cost']], color=["grey", "teal"])
    
    # Adjust title and label fonts
    ax.set_title("Cost Comparison: Model A vs. Model B", fontsize=10)
    ax.set_xlabel("Total Cost", fontsize=10)
    
    # Add data labels in the middle of the bars
    for bar in bars:
        width = bar.get_width()  # Get the width of the bar (total cost)
        ax.text(width / 2, bar.get_y() + bar.get_height() / 2, f"{width:.2f}", 
                color="black", ha="center", va="center", fontsize=10)  # Place text in the middle of the bar
    
    # Set consistent axis limits across both charts
    max_cost = max(model_a['total_cost'], model_b['total_cost'])
    ax.set_xlim(0, max_cost * 1.1)  # Set limits with a small margin on the right
    
    # Adjust layout to prevent clipping
    plt.tight_layout()

    st.pyplot(fig)
