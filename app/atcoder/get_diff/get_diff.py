def get_diff(raw_diff):
  if raw_diff is None:
    return None
  elif raw_diff < 0:
    return 30
  else:
    return raw_diff
