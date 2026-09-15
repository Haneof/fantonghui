import sqlite3, time
con=sqlite3.connect(":memory:")
print("sqlite:", sqlite3.sqlite_version)
# real continuous Chinese text (no spaces) — like actual ASR transcripts
docs=[
 "我妈说下个月是她生日想要个礼物",
 "今天跟老张吃饭聊到借钱的事有点争执",
 "加班熬夜到三点心悸得厉害",
 "妈妈生日礼物我买了围巾她很开心",
]
con.execute("CREATE VIRTUAL TABLE fts_u USING fts5(content, tokenize='unicode61')")
con.executemany("INSERT INTO fts_u(content) VALUES (?)",[(d,) for d in docs])
for term in ["妈妈","生日","礼物","生日 礼物"]:
    n=con.execute("SELECT count(*) FROM fts_u WHERE fts_u MATCH ?",(term,)).fetchone()[0]
    print(f"unicode61 MATCH {term!r:12} -> {n} hits")
print("unicode61 LIKE '%妈妈%' ->", con.execute("SELECT count(*) FROM fts_u WHERE content LIKE '%妈妈%'").fetchone()[0])
try:
    con.execute("CREATE VIRTUAL TABLE fts_t USING fts5(content, tokenize='trigram')")
    con.executemany("INSERT INTO fts_t(content) VALUES (?)",[(d,) for d in docs])
    for term in ["妈妈生日","生日","老张借钱"]:
        n=con.execute("SELECT count(*) FROM fts_t WHERE fts_t MATCH ?",('"'+term+'"',)).fetchone()[0]
        print(f"trigram MATCH \"{term}\" -> {n} hits")
except Exception as e:
    print("trigram unavailable:", e)
