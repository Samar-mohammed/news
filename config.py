"""إعدادات نشرة أخبار الذكاء الاصطناعي اليومية."""

# مصادر RSS. تم اختبار كل رابط والتأكد من أنه يرجع 200.
FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/"),
    ("Wired AI", "https://www.wired.com/feed/tag/ai/latest/rss"),
    ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
    ("MIT News AI", "https://news.mit.edu/rss/topic/artificial-intelligence2"),
]

# النافذة المفضّلة بالساعات. 26 بدل 24 لتغطية أي تأخير في تشغيل الجدولة.
LOOKBACK_HOURS = 26

# حد أقصى للأخبار المرسلة للنموذج، للتحكم في التكلفة.
MAX_ENTRIES_TO_MODEL = 40

# حد أقصى للأخبار لكل مصدر، حتى لا يبتلع مصدر نشيط النشرة كلها.
MAX_ENTRIES_PER_FEED = 12

# طول وصف الخبر المرسل للنموذج، بالأحرف.
MAX_SUMMARY_CHARS = 600

OPENAI_MODEL = "gpt-5-mini"

# مهلة تحميل كل مصدر RSS بالثواني.
FEED_TIMEOUT = 25

# جلب نص المقال الكامل يتم للأخبار المختارة فقط، لأن مقتطف RSS أحيانًا سطر واحد.
ARTICLE_TIMEOUT = 20
ARTICLE_FETCH_WORKERS = 8
# حد أعلى لطول النص المرسل للنموذج، لضبط التوكنات.
MAX_ARTICLE_CHARS = 4000
# نص أقصر من هذا يعني جدار دفع أو صفحة فارغة، فنعود لمقتطف RSS.
MIN_ARTICLE_CHARS = 250

# مدة الاحتفاظ بروابط الأخبار المرسلة في الذاكرة.
SEEN_RETENTION_DAYS = 30

HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# التوقيت المستخدم في عنوان الإيميل وتاريخه.
DISPLAY_TIMEZONE_OFFSET_HOURS = 3
DISPLAY_TIMEZONE_LABEL = "بتوقيت الرياض"
