import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import textwrap

plt.rcParams['font.family'] = ['Microsoft JhengHei', 'Segoe UI', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# ====== 圖1: Feature Check-in Flow ======
fig, ax = plt.subplots(1, 1, figsize=(18, 26), dpi=150)
ax.set_xlim(0, 18)
ax.set_ylim(0, 26)
ax.axis('off')
fig.patch.set_facecolor('#0d1117')
ax.set_facecolor('#0d1117')

# 顏色
C = {
    'decision': '#1f6feb', 'process': '#6e40c9', 'verify': '#da3633',
    'pass': '#238636', 'warn': '#f0883e', 'text': '#e6edf3',
    'dim': '#8b949e', 'bg': '#161b22', 'border': '#30363d',
    'blue': '#58a6ff', 'red_light': '#f85149',
}

def rbox(ax, x, y, w, h, fc, text_lines, fs=10, title=None):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.15",
                          facecolor=fc, edgecolor='white', linewidth=1.5, alpha=0.90)
    ax.add_patch(box)
    n = len(text_lines)
    line_h = (h - 0.3) / max(n, 1)
    for i, line in enumerate(text_lines):
        weight = 'bold' if (title and i == 0) else 'normal'
        fsize = fs + 1 if (title and i == 0) else fs
        ax.text(x + w/2, y + h - 0.25 - i*line_h - line_h/2, line,
                ha='center', va='center', fontsize=fsize, color='white', fontweight=weight)

def diamond(ax, cx, cy, size, fc, text, fs=9):
    pts = [(cx, cy+size), (cx+size, cy), (cx, cy-size), (cx-size, cy)]
    d = plt.Polygon(pts, facecolor=fc, edgecolor='white', linewidth=1.5, alpha=0.90)
    ax.add_patch(d)
    for i, t in enumerate(text.split('\n')):
        ax.text(cx, cy + (0.15 - i*0.3)*size, t, ha='center', va='center',
                fontsize=fs, color='white', fontweight='bold')

def arr(ax, x1, y1, x2, y2, label=None, lc=None, color=C['dim']):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=2.2))
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx + 0.2, my, label, fontsize=9, color=lc or C['text'], fontweight='bold')

# 標題
ax.text(9, 25.5, 'MTK Modem Check-in 流程', ha='center', fontsize=20,
        color=C['blue'], fontweight='bold')
ax.text(9, 25.0, 'Gen99 / 99R — Feature Check-in Flow', ha='center',
        fontsize=11, color=C['dim'])

# === 左側 Non-target ===
LX = 0.5
rbox(ax, LX, 23.2, 4.5, 0.8, C['pass'], ['RD 有代碼要提交'])

diamond(ax, 2.75, 22, 0.8, C['decision'], 'Step 1\nTarget?')
arr(ax, 2.75, 23.2, 2.75, 22.8)

rbox(ax, LX-0.3, 18.8, 5, 2.3, C['verify'], [
    'Non-target 通道', 'EWSP Binary Compare', 'Case1: MCU 無差異',
    'Case3: DSP bin 無差異', 'Case5: SWARM bypass'], fs=9)
arr(ax, 2.75-0.8, 22-0.8, 2.75-0.8+0.3, 21.1, label='Non-target', lc=C['blue'])

rbox(ax, LX-0.3, 16.7, 5, 1.2, C['pass'], [
    'CR Note 加', '[NON-TARGET_PASS]', '[CASEx][Branch]'], fs=9)
arr(ax, 2.2, 18.8, 2.2, 17.9)

rbox(ax, LX-0.3, 15.2, 5, 1.0, C['pass'], ['CIA2 Auto Approve'], fs=10)
arr(ax, 2.2, 16.7, 2.2, 16.2)

rbox(ax, LX-0.3, 13.8, 5, 1.0, C['process'], ['SWARM All Checkers Pass'], fs=9)
arr(ax, 2.2, 15.2, 2.2, 14.8)

rbox(ax, LX-0.3, 12.4, 5, 0.9, C['pass'], ['P4V Check-in [OK]'], fs=10)
arr(ax, 2.2, 13.8, 2.2, 13.3)

# === 右側 Feature ===
RX = 7
RW = 6

rbox(ax, RX, 20.5, RW, 1.4, C['process'], [
    'Step 2 — 申請 FCIA', 'Jira 開票', '填 Feature 名稱、Branch、著陸計畫'], fs=9)
arr(ax, 2.75+0.8, 22, 5, 21.65, label='Target/Feature', lc=C['blue'])
arr(ax, 5, 21.65, 7, 21.5, color=C['blue'])

arr(ax, RX+RW/2, 20.5, RX+RW/2, 19.7)

rbox(ax, RX, 18.1, RW, 1.5, C['process'], [
    'Step 3 — FCIA 審核', 'PSI pre-review → PL 聯審',
    'Gen PL + SoC PL + L1 lead', 'T= 2~5 Days'], fs=9)

arr(ax, RX+RW/2, 18.1, RX+RW/2, 17.3)

rbox(ax, RX, 15.9, RW, 1.3, C['verify'], [
    'Step 4 — 驗證 GEWSP', '= EWSP [OK] + CI-MTBF [OK]', '≥1H 裝置驗證', 'T= 2~4 Days'], fs=9)

arr(ax, RX+RW/2, 15.9, RX+RW/2, 15.1)

diamond(ax, RX+RW/2, 14.5, 0.9, C['decision'], 'Step 5\nCIA2', fs=9)

# Auto
rbox(ax, RX+RW+0.5, 14.1, 3.2, 0.8, C['pass'], ['Auto Approve', 'Jira Approved + CR ID'], fs=7)
arr(ax, RX+RW/2+0.9, 14.5, RX+RW+0.5, 14.5, label='Auto', lc=C['pass'])

# Manual
rbox(ax, RX-2.5, 13.0, 3.2, 0.8, C['warn'], ['Manual Review', 'BO/PL 審核 T= 1H~1D'], fs=7)
arr(ax, RX+RW/2-0.9, 14.5-0.3, RX-2.5+1.6, 13.8, label='Manual', lc=C['warn'])

# 合流到 Step 6
arr(ax, RX+RW+0.5+1.6, 14.1, RX+RW/2, 12.9)
arr(ax, RX-2.5+1.6, 13.0, RX+RW/2-1, 12.3)

rbox(ax, RX, 11.3, RW, 1.6, C['process'], [
    'Step 6 — SWARM Review', 'Code Review [OK] CI-MTBF Checker [OK]',
    'Binary Compare [OK] Keyword Scan [OK]', 'T= 1H~1Day'], fs=9)

arr(ax, RX+RW/2, 11.3, RX+RW/2, 10.5)

rbox(ax, RX+0.8, 9.7, RW-1.6, 0.7, C['pass'], ['Step 7 -- P4V Check-in >>'], fs=11)
arr(ax, RX+RW/2, 9.7, RX+RW/2, 9.0)

rbox(ax, RX+0.8, 8.2, RW-1.6, 0.7, C['pass'], ['Step 8 -- FCIA -> Done'], fs=10)
arr(ax, RX+RW/2, 8.2, RX+RW/2, 7.5)

rbox(ax, RX+0.5, 6.6, RW-1, 0.8, C['warn'], [
    '*Complete PSDLC (Security)', '不擋 Check-in 但必須完成'], fs=8)

# 效期框
vb = FancyBboxPatch((RX+0.2, 5.6), RW-0.4, 0.7, boxstyle="round,pad=0.08",
                      facecolor=C['bg'], edgecolor=C['warn'], linewidth=1.5, linestyle='--')
ax.add_patch(vb)
ax.text(RX+RW/2, 5.95, '效期：CI-EWSP 7天 | CI-MTBF 7天 | CIA2 Manual 3工作天',
        ha='center', va='center', fontsize=8, color=C['warn'], fontweight='bold')

# 底部警告
wb = FancyBboxPatch((1, 0.3), 16, 1.0, boxstyle="round,pad=0.1",
                      facecolor='#2d1515', edgecolor=C['verify'], linewidth=2)
ax.add_patch(wb)
ax.text(9, 0.8, '!!  改 MCF (MOS enable/disable) 影響 SQC Load → 禁走 Non-target → 必須走 Feature Flow 申請 FCIA',
        ha='center', va='center', fontsize=10, color=C['verify'], fontweight='bold')

# === Bug Fix Quick Path 補充圖 (右下) ===
bx, by = 0.5, 1.8
rbox(ax, bx, by, 3, 0.6, C['pass'], ['CI 通\n(編譯+Sanity)'], fs=7)
rbox(ax, bx+3.3, by, 3, 0.6, C['verify'], ['CI-MTBF 通\n(≥1H驗證)'], fs=7)
rbox(ax, bx+6.6, by, 3, 0.6, C['verify'], ['EWSP 通\n(Binary Compare)'], fs=7)
rbox(ax, bx+9.9, by, 2.2, 0.6, C['pass'], ['CIA2 Auto'], fs=7)
rbox(ax, bx+12.3, by, 2.2, 0.6, C['process'], ['SWARM'], fs=7)
rbox(ax, bx+14.7, by, 2, 0.6, C['pass'], ['P4V [OK]'], fs=7)

for i in range(5):
    ax.annotate('', xy=(bx+3.3+i*3.3*(i<2)+2.2*(i>=2 and i<4)+2*(i==4), by+0.3),
                xytext=(bx+3+i*3.3*(i<2)+2.2*(i>=2 and i<4)+2*(i==4), by+0.3),
                arrowprops=dict(arrowstyle='->', color=C['dim'], lw=1.5))

ax.text(bx+8, by+0.95, 'Bug Fix Quick Path（免 FCIA）', ha='center',
        fontsize=9, color=C['blue'], fontweight='bold')

plt.tight_layout(pad=0.3)
out1 = 'D:/01_Job/Tool/Hermes Agent/checkin_flow_full.png'
fig.savefig(out1, facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=150)
print(f'Saved: {out1}')
plt.close()

# ====== 圖2: MOS / MCF / SBP 關係 ======
fig2, ax2 = plt.subplots(1, 1, figsize=(14, 8), dpi=150)
ax2.set_xlim(0, 14)
ax2.set_ylim(0, 8)
ax2.axis('off')
fig2.patch.set_facecolor('#0d1117')
ax2.set_facecolor('#0d1117')

ax2.text(7, 7.5, 'MOS / MCF / SBP 關係圖', ha='center', fontsize=18,
         color=C['blue'], fontweight='bold')
ax2.text(7, 7.0, '配置層 — 非流程環節，但是影響流程選擇', ha='center',
         fontsize=10, color=C['dim'])

# MOS
rbox(ax2, 1, 5.5, 3.5, 1.0, C['decision'], ['MOS', 'Modem Option Switch', '編譯開關管理平台'], fs=9)
# MCF
rbox(ax2, 5, 3.5, 3.5, 1.0, C['process'], ['MCF', 'Modem Compile Feature', '編譯特性開關'], fs=9)
# SBP
rbox(ax2, 1, 3.5, 3.5, 1.0, C['pass'], ['SBP', 'Subscriber Profile', '客戶設定檔'], fs=9)
# SQC
rbox(ax2, 9.5, 3.5, 3.5, 1.0, C['verify'], ['SQC Binary 內容', '與負載'], fs=9)
# IMS
rbox(ax2, 9.5, 5.5, 3.5, 1.0, C['warn'], ['IMS/SIP', '客戶行為'], fs=9)

# 箭頭
arr(ax2, 2.75+0.2, 5.5, 2.75+0.2, 4.5)
ax2.text(3.3, 5.0, 'enable/\ndisable', fontsize=7, color=C['text'], ha='left', va='center')

arr(ax2, 4.5, 4.0, 5, 4.0)
ax2.text(4.7, 4.3, '定義\n開關', fontsize=7, color=C['text'], ha='center', va='bottom')

arr(ax2, 6.75, 4.0, 7.2, 4.0)
ax2.text(7.0, 4.3, '影響', fontsize=8, color=C['verify'], ha='center', va='bottom', fontweight='bold')

arr(ax2, 8.5, 4.0, 9.2, 4.5)
ax2.text(9.0, 5.0, '讀取', fontsize=7, color=C['text'], ha='center')

arr(ax2, 4.5, 6.0, 5, 6.0)
ax2.text(4.7, 5.6, '關聯', fontsize=7, color=C['dim'], ha='center')

# 警告框
wb2 = FancyBboxPatch((1, 1.2), 12, 1.5, boxstyle="round,pad=0.1",
                       facecolor='#2d1515', edgecolor=C['verify'], linewidth=2)
ax2.add_patch(wb2)
ax2.text(7, 1.95, '!!  改 MCF (在 MOS 上 enable/disable)', ha='center',
         fontsize=10, color=C['verify'], fontweight='bold')
ax2.text(7, 1.55, '影響 SQC Load → 不能走 Non-target 通道 → 必須走 Feature Check-in Flow', ha='center',
         fontsize=9, color='white')

# SBP 檔案路徑
ax2.text(2.75, 2.9, 'sbp_id.def / sbp_nvram_vdm_config\nims_config folder', ha='center',
         fontsize=7, color=C['dim'], style='italic')

plt.tight_layout(pad=0.3)
out2 = 'D:/01_Job/Tool/Hermes Agent/checkin_mcf_relation.png'
fig2.savefig(out2, facecolor=fig2.get_facecolor(), bbox_inches='tight', dpi=150)
print(f'Saved: {out2}')
plt.close()

print('DONE')
