import lxml.html
from curl_cffi import requests as cffirequests
import re
import json
from lxml import etree
import html
import datetime
from bs4 import BeautifulSoup
import base64
from concurrent.futures import ThreadPoolExecutor,as_completed
import random
import pymysql
import time


def quotedStr(strtext):
    strtext=str(strtext)
    return "\""+strtext+"\""

def get_proxy(type):

    if type==1:

        proxy_host =random.choice(proxy_proxy_host_list)
        proxy_port = proxy_proxy_port
        proxy_username = proxy_proxy_username
        proxy_pwd = proxy_proxy_pwd


        proxyMeta = "http://%(user)s:%(pass)s@%(host)s:%(port)s" % {
            "host": proxy_host,
            "port": proxy_port,
            "user": proxy_username,
            "pass": proxy_pwd,
        }
        proxies = {
            'http': proxyMeta,
            'https': proxyMeta,
        }
        return proxies
    else:
        proxies = {}
        return proxies

def get_questions(project_info):
    pid = project_info["pid"]
    project_url = project_info["project_url"]
    project_id = project_info["project_id"]
    resultdata = {"pid": pid, "success": 0, "project_link": project_url, "project_id": project_id}
    try:
        questionsoldurl=project_url.split("?", 1)[0]
        questionsurl=questionsoldurl+"/faqs"

        slugs = re.search(r'com/projects/(.+)', questionsoldurl)
        if slugs:
           slug = slugs.group(1)
        else:
            return {"pid": pid, "success": 1}

        cookies=global_cookies.copy()
        cookies["_ksr_session"]=global_param["session"]

        impersonate_item = random.choice(impersonate_list)
        user_agent_item = random.choice(user_agent_list)
        proxiesip = get_proxy(Use_proxy)

        headers=global_headers.copy()
        headers["referer"]=questionsurl
        headers["x-csrf-token"]=global_param["csrf_token"]
        headers["user-agent"] = user_agent_item

        json_data = [
            {
                'operationName': 'Campaign',
                'variables': {
                    'slug': slug,
                },
                'query': 'query Campaign($slug: String!) {\n  project(slug: $slug) {\n  faqs {\n  nodes {id\n  question\n  answer\n  createdAt\n  updatedAt\n}  }\n }\n }\n',
            },
        ]

        response = cffirequests.post('https://www.kickstarter.com/graph',
                                     cookies=cookies,
                                     headers=headers,
                                     json=json_data,
                                     impersonate=impersonate_item,
                                     proxies=proxiesip)


        if response.status_code == 200:

            # with open("questions.json", "w", encoding="utf-8") as fout:
            #     fout.write(response.text)


            jsondata = json.loads(response.text)
            project_data = jsondata[0]["data"]["project"]
            if project_data is None:
                    return {"pid": pid, "success": 1, "project_link": project_url, "project_id": project_id}


            faqsnode=project_data["faqs"]
            if faqsnode is None:
                    return {"pid": pid, "success": 1, "project_link": project_url, "project_id": project_id}

            questionlistdata=[]
            if "nodes" in project_data["faqs"] and project_data["faqs"]["nodes"]:
                faqslists=project_data["faqs"]["nodes"]
                if faqslists:
                    row_num=0
                    for faqslist in faqslists:
                        row_num+=1
                        question=""
                        answer=""
                        last_updated_time=""


                        if faqslist["question"]:
                            question=faqslist["question"]

                        if faqslist["answer"]:
                            answer=faqslist["answer"]

                        if faqslist["answer"]:
                            last_updated_stamp=faqslist["updatedAt"]
                            last_updated_dt = datetime.datetime.fromtimestamp(last_updated_stamp)
                            last_updated_time = last_updated_dt.strftime('%Y-%m-%d %H:%M:%S')

                        questionlistdata.append({
                            "row_num":row_num,
                            "question":question,
                            "answer":answer,
                            "last_updated_time":last_updated_time
                        })

            resultdata["questionlist"]=questionlistdata
            resultdata["success"]=1

    except Exception as e:
        print("报错:", project_url,str(e))
        resultdata={"pid": pid, "success": 0}

    return resultdata

def downloadquestionsinfo():
    retry_number=0
    while True:
        db = get_mysqldb()
        cursor = db.cursor()


        # end_postion = begin_postion+10000
        begin_postion=0
        end_postion=1000000

        querysql = """
                   select a.pid,a.project_id, a.project_url  from crawling_url a  where a.pid >=%s  AND a.pid<%s  and a.question=0     LIMIT 2000
                   """ % (begin_postion, end_postion)

        cursor.execute(querysql)  # 执行SQL语句
        scrapy_urls = cursor.fetchall()
        db.close()

        if retry_number>1000:
            get_requests_param()
            retry_number=0


        if len(scrapy_urls) == 0:
            break

        else:
            try:
                db = get_mysqldb()
                with ThreadPoolExecutor(max_workers=Max_works) as t1:

                    obj_list1 = []
                    for scrapy_url in scrapy_urls:
                        obj_list1.append(t1.submit(get_questions,scrapy_url))

                    for future in as_completed(obj_list1):
                        retrunrewards = future.result()

                        if retrunrewards["success"] == 1:
                            try:
                                cursor = db.cursor()
                                link_pid = retrunrewards["pid"]
                                if "questionlist" in  retrunrewards and  retrunrewards["questionlist"]:
                                    questionlistinfo = retrunrewards["questionlist"]

                                    insertquestionsql = """ insert into questions_info(pid,project_id,project_link,row_num,question,
                                                                                           answer) 
                                                                                       VALUES(%s,%s,%s,%s,%s,%s) 
                                              """
                                    questionlists = []
                                    for questioninfo in questionlistinfo:
                                        questionlists.append((retrunrewards["pid"], retrunrewards["project_id"],retrunrewards["project_link"],
                                                              questioninfo["row_num"], questioninfo["question"],questioninfo["answer"]
                                                               ))

                                    cursor.executemany(insertquestionsql, questionlists)  # 执行SQL语句


                                updatesql = """update crawling_url set question=1 where pid=%s """ % link_pid
                                cursor.execute(updatesql)
                                db.commit()  # 提交
                                print("question下载成功!")

                            except Exception as e:
                                print(str(e))
                                db.rollback()  # 如果执行失败要回滚

            finally:
                db.close()
def get_mysqldb():
    try:

        db = pymysql.connect(host=db_host,
                             port = db_port,
                             user=  db_user,
                             password =db_password,
                             database = db_database,
                             charset = "utf8mb4",
                             connect_timeout=60,
                             cursorclass=pymysql.cursors.DictCursor)
        # print("数据库连接成功")
        return db
    except Exception as e:
        print("数据库连接失败:",str(e))

def get_requests_param():
    expiration=False
    while True:
        impersonate_item=random.choice(impersonate_list)
        user_agent_item = random.choice(user_agent_list)
        headers = {
            'authority': 'www.kickstarter.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'zh-CN,zh;q=0.9',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
        }

        headers["user-agent"] = user_agent_item
        proxiesip = get_proxy(Use_proxy)
        try:
            response = cffirequests.get('https://www.kickstarter.com', cookies=global_cookies,
                                        headers=headers, impersonate=impersonate_item, proxies=proxiesip)

            if response.status_code==200:
                cookiejar = response.cookies
                global_param["session"]=cookiejar["_ksr_session"]

                htmlpage = etree.HTML(response.text)
                csrf_token=""
                csrf_token_node = htmlpage.xpath('//meta[@name="csrf-token"]/@content')
                if csrf_token_node:
                    csrf_token = str(csrf_token_node[0])

                global_param["csrf_token"]=csrf_token

                break;
            else:
                print("访问网站失败",response.status_code)
                time.sleep(1)
        except Exception as e:
            print("连接代理服务器失败")
            time.sleep(1)

    return expiration


if __name__ == '__main__':
    with open("config.json", "r", encoding="utf-8") as fin:
        configtext = fin.read()
        configtext = configtext.strip()

    configjson = json.loads(configtext)

    db_host = configjson["db_config"]["host"]
    db_port = configjson["db_config"]["port"]
    db_user = configjson["db_config"]["user"]
    db_password = configjson["db_config"]["password"]
    db_database = configjson["db_config"]["database"]

    proxy_proxy_host_list = configjson["proxy_config"]["proxy_host_list"]
    proxy_proxy_port = configjson["proxy_config"]["proxy_port"]
    proxy_proxy_username = configjson["proxy_config"]["proxy_username"]
    proxy_proxy_pwd = configjson["proxy_config"]["proxy_pwd"]
    proxy_enable_proxy = configjson["proxy_config"]["enable_proxy"]

    max_threads = configjson["max_threads"]

    impersonate_list = ["edge99", "edge101", "chrome99", "chrome101", "chrome104", "chrome107", "chrome110",
                        "chrome116", "chrome119","chrome120","safari15_3", "safari15_5", "safari17_0",
                        "safari17_2_ios", "chrome99_android"]


    user_agent_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 OPR/117.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) obsidian/1.6.5 Chrome/124.0.6367.243 Electron/30.1.2 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/116.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) obsidian/1.8.4 Chrome/130.0.6723.191 Electron/33.3.2 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1.1 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) obsidian/1.8.3 Chrome/130.0.6723.191 Electron/33.3.2 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) obsidian/1.6.5 Chrome/124.0.6367.243 Electron/30.1.2 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.5938.132 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.5938.92 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) obsidian/1.8.4 Chrome/130.0.6723.191 Electron/33.3.2 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:134.0) Gecko/20100101 Firefox/134.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/115.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.137 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0",
        "Mozilla/5.0 (X11; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.2903.86",
        "Mozilla/5.0 (Windows NT 10.0; rv:135.0) Gecko/20100101 Firefox/135.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) obsidian/1.7.7 Chrome/128.0.6613.186 Electron/32.2.5 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) obsidian/1.6.7 Chrome/124.0.6367.243 Electron/30.1.2 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) obsidian/1.7.7 Chrome/128.0.6613.186 Electron/32.2.5 Safari/537.36"
    ]
    global_param={"csrf_token":"","session":""}


    global_cookies = {'lang': 'en'}


    global_headers = {
        'authority': 'www.kickstarter.com',
        'accept': '*/*',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-TW;q=0.5',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'origin': 'https://www.kickstarter.com',
        'pragma': 'no-cache',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin'
    }

    Use_proxy=proxy_enable_proxy
    Max_works=max_threads

    get_requests_param()

    # bbb=get_questions({"pid":1,"project_id":2,"project_url":"https://www.kickstarter.com/projects/hidsips/hydralamp-a-modern-solution-to-bedside-hydration?ref=discovery_category_newest"})
    # abc=json.dumps(bbb)
    # with open("page.json", "w", encoding="utf-8") as fout:
    #     fout.write(abc)

    downloadquestionsinfo()


