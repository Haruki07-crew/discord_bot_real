"""期間内の累積AC数の推移 (/syozin graph)。横軸が時刻、縦軸がその時点までの累積AC数。"""
import io
from datetime import datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from atcoder import db
from atcoder.count_period_ac import get_period_start_unix

JST = timezone(timedelta(hours=9))


def get_cumulative_ac_series(atcoder_name, day, db_file, kind="total"):
  """期間内の [(Unix秒, 累積AC数), ...] を時刻順に返す。
  kind="total" は総合AC ((問題, JSTの日付) ごとに1回。count_period_ac と同じ数え方)、
  kind="new" は新規AC (期間内に初めて AC した問題)。最後の値は count_period_ac の値と一致する。"""
  start = get_period_start_unix(day)
  with db.connect(db_file) as conn:
    if kind == "new":
      rows = conn.execute("""
        SELECT first_ac FROM (
          SELECT MIN(epoch_second) AS first_ac FROM ac_submissions_cache
          WHERE atcoder_name = ? GROUP BY problem_id
        ) WHERE first_ac >= ? ORDER BY first_ac
      """, (atcoder_name, start)).fetchall()
    else:
      rows = conn.execute("""
        SELECT MIN(epoch_second) AS t FROM ac_submissions_cache
        WHERE atcoder_name = ? AND epoch_second >= ?
        GROUP BY problem_id, date(epoch_second, 'unixepoch', '+9 hours')
        ORDER BY t
      """, (atcoder_name, start)).fetchall()
  return [(t, i + 1) for i, (t,) in enumerate(rows)]


def create_cumulative_ac_graph(series_by_user, day, title, now=None):
  """series_by_user: {表示名: [(Unix秒, 累積AC数), ...]}。階段状の折れ線で描く。
  全員が0件なら None を返す。"""
  if not any(series_by_user.values()):
    return None
  try:
    import japanize_matplotlib as _japanize
    _japanize
  except ImportError:
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "IPAexGothic", "DejaVu Sans", "sans-serif"]
  from atcoder.create_weekly_graph import COLORS as colors

  start = datetime.fromtimestamp(get_period_start_unix(day), JST)
  end = datetime.fromtimestamp(now, JST) if now is not None else datetime.now(JST)
  fig, ax = plt.subplots(figsize=(10, 6))
  fig.patch.set_facecolor("white")
  ax.set_facecolor("#f8f9fa")

  # 最後の値が大きい順に並べると、凡例が順位と同じ並びになる
  ordered = sorted(series_by_user.items(), key=lambda kv: kv[1][-1][1] if kv[1] else 0, reverse=True)
  for i, (name, series) in enumerate(ordered):
    xs = [start] + [datetime.fromtimestamp(t, JST) for t, _ in series] + [end]
    ys = [0] + [n for _, n in series] + [series[-1][1] if series else 0]
    ax.step(xs, ys, where="post", label=f"{name} ({ys[-1]})", color=colors[i % len(colors)], linewidth=2, zorder=3)

  ax.set_xlim(start, end)
  ax.set_ylim(bottom=0)
  ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M" if day <= 1 else "%m/%d", tz=JST))
  fig.autofmt_xdate()
  ax.set_ylabel("累積AC数", fontsize=12)
  ax.set_title(title, fontsize=14, fontweight="bold")
  ax.legend(loc="upper left", fontsize=10)
  ax.grid(True, alpha=0.3, zorder=1)

  buf = io.BytesIO()
  plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
  buf.seek(0)
  plt.close(fig)
  return buf
