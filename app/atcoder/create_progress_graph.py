import matplotlib.pyplot as plt
import io

def create_progress_graph(all_user_data):
  try:
    import japanize_matplotlib as _japanize
    _japanize
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

  has_data = False
  for i, (atcoder_name, points) in enumerate(all_user_data.items()):
    if points is None or len(points) < 2:
      continue
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    color = colors[i % len(colors)]
    ax.plot(xs, ys, marker='o', label=atcoder_name, color=color, linewidth=2, markersize=8, zorder=3)
    has_data = True

  if not has_data:
    plt.close()
    return None

  ax.set_xlabel("AC数", fontsize=12)
  ax.set_ylabel("レート", fontsize=12)
  ax.set_title("精進レートグラフ", fontsize=14, fontweight='bold')
  ax.legend(loc='best', fontsize=10)
  ax.grid(True, alpha=0.3, zorder=1)

  buf = io.BytesIO()
  plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
  buf.seek(0)
  plt.close()
  return buf
