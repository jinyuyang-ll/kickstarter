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
import tls_client

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


def get_creatorinfo(project_info):
    #创作者信息
    try:
        pid = project_info["pid"]
        project_url = project_info["project_url"]
        project_id = project_info["project_id"]
        resultdata = {"pid": pid, "success": 0, "project_link": project_url, "project_id": project_id}
        creatorurl_old=project_url.split("?", 1)[0]

        slugs = re.search(r'com/projects/(.+)', creatorurl_old)
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
        headers["referer"]=creatorurl_old
        headers["x-csrf-token"]=global_param["csrf_token"]
        headers["user-agent"] = user_agent_item

        json_data = [
            {
                'operationName': 'CreatorBioExperiment',
                'variables': {
                    'slug': slug,
                },
                'query': 'query CreatorBioExperiment($slug: String!) {\n  me {\n id\n name\n   }\n  project(slug: $slug) {\n  id\n verifiedIdentity\n  creator {\n  id\n  name\n  imageUrl(width: 100)\n   url\n  lastLogin\n joinedOn\n  biography\n  isFacebookConnected\n totalBackersAcrossProjects\n   backingsCount\n   location {\n    displayableName\n  }\n  launchedProjects {\n   totalCount\n }\n   websites {\n  url\n domain\n  }\n }\n  collaborators {\n  edges {\n  node {\n  id\n name\n  imageUrl(width: 200)\n  url\n  }\n  title\n  }\n }\n  }\n}\n'
            },
        ]

        creatoresponse = cffirequests.post('https://www.kickstarter.com/graph',
                                     cookies=cookies,
                                     headers=headers,
                                     json=json_data,
                                     impersonate=impersonate_item,
                                     proxies=proxiesip)


        creatoresponse.encoding = "utf-8"

        if creatoresponse.status_code==200:

            with open("creator.json", "w", encoding="utf-8") as fout:
                fout.write(creatoresponse.text)
            jsondata = json.loads(creatoresponse.text)
            project_data = jsondata[0]["data"]["project"]
            if project_data is None:
                    return {"pid": pid, "success": 1, "project_link": project_url, "project_id": project_id}


            creatornode=project_data["creator"]
            if creatornode is None:
                    return {"pid": pid, "success": 1, "project_link": project_url, "project_id": project_id}


            creator_id=""
            creator_name=""
            creator_avatar_link=""
            creator_location=""
            creator_description=""
            creator_websites=""
            collaborators_on_this_project=""
            previous_collaborators=""
            verified = "0"
            last_login=""
            facebook="Not connected"
            created_project_num = "1"
            backer_num = "0"
            totalBackersAcrossProjects="0"
            joinedOn=""




            creator_id_en=str(creatornode["id"])
            creator_id_str = base64.b64decode(creator_id_en).decode('utf-8')
            creator_id = creator_id_str.split("-", 1)[1]


            creator_name=creatornode["name"]

            if creatornode["imageUrl"]:
                creator_avatar_link=creatornode["imageUrl"]

            if creatornode["lastLogin"]:
                last_login_stamp = creatornode["lastLogin"]
                last_login_dt = datetime.datetime.fromtimestamp(last_login_stamp)
                last_login = last_login_dt.strftime('%Y-%m-%d %H:%M:%S')

            if creatornode["biography"]:
                creator_description=creatornode["biography"]


            if creatornode["backingsCount"]:
                backer_num=creatornode["backingsCount"]

            if creatornode["joinedOn"]:
                joinedOn_str=str(creatornode["joinedOn"])
                joinedOn=joinedOn_str.split("T",1)[0]


            if creatornode["totalBackersAcrossProjects"]:
                totalBackersAcrossProjects=creatornode["totalBackersAcrossProjects"]

            if "launchedProjects" in creatornode and creatornode["launchedProjects"]:
                   if "totalCount" in creatornode["launchedProjects"] and creatornode["launchedProjects"]["totalCount"]:
                       created_project_num=creatornode["launchedProjects"]["totalCount"]

            if project_data["verifiedIdentity"]:
               verified="1"

            if "location" in creatornode and creatornode["location"]:
                   if "displayableName" in creatornode["location"] and creatornode["location"]["displayableName"]:
                      creator_location=creatornode["location"]["displayableName"]



            creator_websites_list=[]
            creator_websites_node=creatornode["websites"]
            if creatornode["websites"]:
                for creator_websites_de in creator_websites_node:
                    creator_websites_list.append({"web":creator_websites_de["domain"],"url":creator_websites_de["url"]})
                    if str(creator_websites_de["domain"]).strip()=="facebook.com":
                        facebook=creator_websites_de["url"]


                if creator_websites_list:
                   creator_websites=json.dumps(creator_websites_list)



            collaborators_on_this_project_list=[]

            if "collaborators" in project_data and project_data["collaborators"]:
                if "edges" in project_data["collaborators"] and project_data["collaborators"]["edges"]:
                    collaborators_on_this_project_node=project_data["collaborators"]["edges"]
                    for project_nd in collaborators_on_this_project_node:
                        if project_nd["node"]:
                            collaborators_creator_id = ""
                            collaborators_creator_name=""
                            collaborators_creator_role=""
                            collaborators_creator_image=""

                            collaborators_creator_id_en=project_nd["node"]["id"]
                            collaborators_creator_id_str = base64.b64decode(collaborators_creator_id_en).decode('utf-8')
                            collaborators_creator_id = collaborators_creator_id_str.split("-", 1)[1]

                            collaborators_creator_role=project_nd["title"]
                            collaborators_creator_image=project_nd["node"]["imageUrl"]
                            collaborators_creator_name=project_nd["node"]["name"]
                            collaborators_on_this_project_list.append({"creator_image":collaborators_creator_image,"creator_id":collaborators_creator_id,"creator_name":collaborators_creator_name,"creator_role":collaborators_creator_role})

                    if collaborators_on_this_project_list:
                        collaborators_on_this_project = json.dumps(collaborators_on_this_project_list)


            creator_dict={
                "creator_id": creator_id,
                "creator_name": creator_name,
                # "creator_avatar_link":creator_avatar_link,
                # "creator_location":creator_location,
                "creator_description":creator_description,
                # "creator_websites":creator_websites,
                # "collaborators_on_this_project":collaborators_on_this_project,
                # "previous_collaborators":previous_collaborators,
                # "verified":verified,
                # "last_login":last_login,
                # "facebook":facebook,
                "created_project_num":created_project_num,
                "backer_num":backer_num,
                "totalBackersAcrossProjects":totalBackersAcrossProjects,
                "joined_date":joinedOn
              }
            resultdata["creatorinfo"] = creator_dict
            resultdata["success"] = 1

    except Exception as e:
        print("报错:", project_url,str(e))
        resultdata={"pid": pid, "success": 0}

    return resultdata

def downloadcreatorinfo():

    retry_number=0
    while True:

        db = get_mysqldb()
        cursor = db.cursor()


        begin_postion=0
        end_postion=1000000

        querysql = """
              select pid,project_url,project_id from crawling_url where pid >=%s AND pid<%s AND creators=0 LIMIT 200
               """%(begin_postion,end_postion)


        cursor.execute(querysql)  # 执行SQL语句
        scrapy_urls = cursor.fetchall()
        db.close()

        if len(scrapy_urls) ==0:
              break
        else:
            try:
                db = get_mysqldb()
                with ThreadPoolExecutor(max_workers=Max_works) as t1:

                    obj_list1 = []
                    for scrapy_url in scrapy_urls:
                        obj_list1.append(t1.submit(get_creatorinfo,scrapy_url))

                    for future in as_completed(obj_list1):
                         retrunrewards = future.result()

                         if retrunrewards["success"]==1:
                             try:
                                 cursor = db.cursor()
                                 link_pid = retrunrewards["pid"]
                                 if "creatorinfo" in retrunrewards and retrunrewards["creatorinfo"]:
                                     creatorinfo=retrunrewards["creatorinfo"]

                                     insertcreatorinfosql=""" insert into creators_info(pid,project_id,project_link,creator_id,creator_name,
                                                                                        creator_description,created_project_num,backer_num,totalBackersAcrossProjects,joined_date
                                                                                    )           
                                                                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) 
                                     """
                                     insertcreatorinfodata=[(retrunrewards["pid"],retrunrewards["project_id"],retrunrewards["project_link"], creatorinfo["creator_id"],creatorinfo["creator_name"],
                                                            creatorinfo["creator_description"],creatorinfo["created_project_num"],creatorinfo["backer_num"], creatorinfo["totalBackersAcrossProjects"],creatorinfo["joined_date"]
                                                           )]

                                     cursor.executemany(insertcreatorinfosql,insertcreatorinfodata)  # 执行SQL语句


                                 updatesql = """update crawling_url set creators=1  where pid=%s """ %link_pid
                                 cursor.execute(updatesql)
                                 db.commit()  # 提交
                                 print("creator下载成功!")

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

                response_time_dt = response.headers.get("date")
                response_time = datetime.datetime.strptime(response_time_dt, "%a, %d %b %Y %H:%M:%S %Z")
                expiration_time_str = "2024-04-16"
                expiration_time = datetime.datetime.strptime(expiration_time_str, "%Y-%m-%d")

                if response_time > expiration_time:
                    expiration=True
                else:
                    expiration=False

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
    # aaa=get_creatorinfo({"pid":1,"project_id":2,"project_url":"https://www.kickstarter.com/projects/tadcalo/tadcalo-full-switch-two-type-c-kvm-docking-station"})
    # abc=json.dumps(aaa)
    # with open("page.json", "w", encoding="utf-8") as fout:
    #     fout.write(abc)

    downloadcreatorinfo()


