"""設計 token：CSS 與 ECharts option 共用同一份顏色，兩邊不會漂移。"""
BG, CARD, INK, INK2, INK3, RULE = "#F3F5F8", "#FFFFFF", "#1F2937", "#5B6475", "#9AA3AF", "#E3E7EE"
SIDE, ACCENT, SIGNAL = "#1E2735", "#2563EB", "#E8590C"
BAD, WARN, OK, NODATA = "#DC2626", "#F59E0B", "#16A34A", "#E5E7EB"
PLAN, FU = "#93C5FD", "#0D9488"
PLAN_MARK = "#7C3AED"    # BU plan 短橫線：與人數線（INK）區分
PLAN_TEXT = "#6D28D9"    # Plan 標籤文字：比短橫線深一階，與 No budget／Actual 標籤同等清楚
HEAT_LOW, HEAT_MID, HEAT_HI = "#FED7AA", "#DBEAFE", "#BFDBFE"   # 閒置產能＝橘（訊號，與部門表一致）；滿載是常態＝藍色深淺，不用紅
HEAT_HIGH = 95          # 熱度表色階分界（顯示用，不是規則；低門檻沿用 thresholds 的 spare_capacity_pct）
NOT_IN_BRIEFING = "Not in Briefing"
BLANK = "(blank)"
PALETTE = ("#2563EB", "#16A34A", "#F59E0B", "#0EA5E9", "#7C3AED", "#DB2777", "#0D9488", "#64748B")   # 類別用色，依排名分配
MS_COLORS = {"evt": "#3B82F6", "dvt": "#16A34A", "pvt": "#F59E0B", "mp": "#DC2626"}   # Timeline 里程碑：照 mock（◇ 藍、◆ 綠、▲ 橘、★ 紅）
TYPE_COLORS = {"ODM": "#2563EB", "EMS": "#0D9488", "JDM": "#F59E0B"}
STAGE_COLORS = {"RFQ / RFI": "#F59E0B", "POC": "#0EA5E9", "Execution": "#2563EB", "MP": "#16A34A", "Sustain / EOP": "#64748B",
                "Terminated": "#9CA3AF", "Suspended": "#7C3AED", "Other": "#A8A29E", NOT_IN_BRIEFING: "#D1D5DB"}
