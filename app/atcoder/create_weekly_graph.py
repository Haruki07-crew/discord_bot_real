import matplotlib.pyplot as plt
import io


# ユーザー間で色がはっきり区別できるパレット
COLORS = [
  '#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4',
  '#42d4f4', '#f032e6', '#bfef45', '#fabed4', '#469990',
  '#dcbeff', '#9A6324', '#800000', '#aaffc3', '#808000',
  '#000075', '#a9a9a9', '#e6beff', '#fffac8', '#ffd8b1',
]


def create_weekly_graph(snapshots, week_number, x_axis="ac"):
  """累積折れ線グラフを生成する。

  Args:
    snapshots: {atcoder_name: [(week, ac_count, ac_point, rate_change), ...]}
    week_number: 現在の週番号 (タイトル用)
    x_axis: "ac" なら累積AC数、"point" なら累積点数を横軸に使う

  Returns:
    BytesIO (PNG画像) or None
  """
  try:
    import japanize_matplotlib as _japanize
    _japanize
  except ImportError:
    plt.rcParams['font.family'] = ['Noto Sans CJK JP', 'IPAexGothic', 'DejaVu Sans', 'sans-serif']

  fig, ax = plt.subplots(figsize=(10, 6))
  fig.patch.set_facecolor('white')
  ax.set_facecolor('#f8f9fa')

  has_data = False
  for i, (name, weeks) in enumerate(snapshots.items()):
    if not weeks:
      continue

    cum_ac = 0
    cum_point = 0
    cum_rc = 0
    xs = []
    ys = []

    for _week, ac, point, rc in weeks:
      cum_ac += ac
      cum_point += point
      cum_rc += rc
      if x_axis == "point":
        xs.append(cum_point)
      else:
        xs.append(cum_ac)
      ys.append(cum_rc)

    color = COLORS[i % len(COLORS)]
    ax.plot(xs, ys, marker='o', label=name, color=color,
            linewidth=2.5, markersize=9, zorder=3)

    # 最後の点にユーザー名を表示
    if xs:
      ax.annotate(name, (xs[-1], ys[-1]),
                  textcoords="offset points", xytext=(8, 4),
                  fontsize=9, fontweight='bold', color=color)

    has_data = True

  if not has_data:
    plt.close()
    return None

  ax.axhline(y=0, color='gray', linestyle='--', linewidth=1, alpha=0.7, zorder=2)

  x_label = "累積点数" if x_axis == "point" else "累積AC数"
  ax.set_xlabel(x_label, fontsize=12)
  ax.set_ylabel("累積レート変化", fontsize=12)

  title_suffix = f"(点数)" if x_axis == "point" else "(AC数)"
  ax.set_title(f"{week_number}週目 {title_suffix}", fontsize=14, fontweight='bold')

  ax.legend(loc='best', fontsize=10)
  ax.grid(True, alpha=0.3, zorder=1)

  buf = io.BytesIO()
  plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
  buf.seek(0)
  plt.close()
  return buf
