import matplotlib.pyplot as plt
import io

def create_ac_rate_graph(user_data, label):
  try:
    import japanize_matplotlib as japanize
    japanize
  except ImportError:
    plt.rcParams['font.family'] = ['Noto Sans CJK JP', 'IPAexGothic', 'DejaVu Sans', 'sans-serif']

  fig, ax = plt.subplots(figsize=(10, 6))
  fig.patch.set_facecolor('white')
  ax.set_facecolor('#f8f9fa')

  colors = [
    '#e74c3c', '#3498db', '#2ecc71', '#f39c12',
    '#9b59b6', '#1abc9c', '#e67e22', '#34495e',
    '#e91e63', '#00bcd4'
  ]

  for i, (name, d) in enumerate(user_data.items()):
    ac = d["ac"]
    rc = d["rate_change"]
    color = colors[i % len(colors)]
    ax.scatter(ac, rc, color=color, s=100, zorder=3)
    ax.annotate(name, (ac, rc), textcoords="offset points", xytext=(6, 4), fontsize=9, color=color)

  ax.axhline(y=0, color='gray', linestyle='--', linewidth=1, alpha=0.7, zorder=2)
  ax.set_xlabel("AC数", fontsize=12)
  ax.set_ylabel("レート変化", fontsize=12)
  ax.set_title(f"AC数 vs レート変化 [{label}]", fontsize=14, fontweight='bold')
  ax.grid(True, alpha=0.3, zorder=1)

  buf = io.BytesIO()
  plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
  buf.seek(0)
  plt.close()
  return buf
