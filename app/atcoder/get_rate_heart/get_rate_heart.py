def get_rate_heart(rating):
  if not isinstance(rating, int):
    return "🤍"
  if rating < 400:
    return "🩶d"
  if rating < 800:
    return "🤎"
  if rating < 1200:
    return "💚"
  if rating < 1600:
    return "🩵"
  if rating < 2000:
    return "💙"
  if rating < 2500:
    return "💛"
  if rating < 2800:
    return "🧡"
  return "❤️"
