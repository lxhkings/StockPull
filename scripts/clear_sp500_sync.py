import pymysql
conn = pymysql.connect(host='192.168.8.9', port=3306, user='root', password='18620001807@Aa', database='stocks')
cur = conn.cursor()
cur.execute("DELETE FROM sync_log WHERE ticker IN (SELECT ticker FROM index_constituents WHERE index_id='SP500')")
conn.commit()
print(f'Deleted {cur.rowcount} sync_log records')
conn.close()
