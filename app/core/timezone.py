import pytz

from app.config import settings

# Mesin mengirim jam setempat tanpa zona waktu; semua scan dianggap memakai zona ini.
LOCAL_TZ = pytz.timezone(settings.TIMEZONE)
