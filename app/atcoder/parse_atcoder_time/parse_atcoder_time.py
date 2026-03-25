from datetime import datetime

def parse_atcoder_time(end_time_str):
  try:
    return datetime.strptime(end_time_str, "%Y/%m/%d %H:%M:%S%z")
  except (ValueError, TypeError):
    try:
      return datetime.fromisoformat(end_time_str)
    except (ValueError, TypeError):
      return None
