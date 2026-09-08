import lxml.html
from ast import literal_eval
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
import argparse
import threading


REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 5
REQUEST_DELAY_SECONDS = 2
_thread_local = threading.local()


def get_http_session():
    """每个工作线程复用会话，保持 Cookie 和浏览器身份稳定。"""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = cffirequests.Session()
    return _thread_local.session


def is_security_challenge(response):
    text = (response.text or "")[:20000].lower()
    markers = (
        "captcha", "cf-chl-", "challenge-platform", "verify you are human",
        "security check", "access denied", "人机验证", "安全验证",
    )
    return response.status_code in (403, 429) or any(x in text for x in markers)


def request_project_page(project_url):
    """有限次数重试；遇到风控时返回明确原因，不无限等待。"""
    headers = global_headers.copy()
    headers["user-agent"] = FIXED_USER_AGENT
    proxies = get_proxy(Use_proxy)
    session = get_http_session()
    last_response = None
    reason = "unknown"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"正在请求 [{attempt}/{MAX_RETRIES}]: {project_url}", flush=True)
            response = session.get(
                project_url,
                cookies=global_cookies,
                headers=headers,
                impersonate=FIXED_IMPERSONATE,
                proxies=proxies,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            last_response = response
            response.encoding = "utf-8"
            print(
                f"网站返回状态: {response.status_code}; 最终地址: {response.url}",
                flush=True,
            )
            if response.status_code == 200 and not is_security_challenge(response):
                global_cookies.update(dict(response.cookies))
                return response, ""
            if response.status_code == 404:
                return response, "not_found"
            reason = (
                "security_challenge"
                if is_security_challenge(response)
                else f"http_{response.status_code}"
            )
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            print(f"请求异常: {reason}", flush=True)

        if attempt < MAX_RETRIES:
            delay = RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 2)
            print(f"本次失败({reason})，{delay:.1f} 秒后重试", flush=True)
            time.sleep(delay)
    return last_response, reason



def quotedStr(strtext):
    strtext=str(strtext)
    return "\""+strtext+"\""
def get_mainpage(project_info):


    try:
        pid = project_info["pid"]
        project_url = project_info["project_url"]
        resultdata = {"pid": pid, "success": 0}


        response, failure_reason = request_project_page(project_url)
        if response is None:
            return {
                "pid": pid, "success": 0, "failure_reason": failure_reason,
                "status_code": None,
            }




        #
        #
        # with open("test.html", "w", encoding="utf-8") as fout:
        #     fout.write(response.text)

        # with open("test.html", "r", encoding="utf-8") as fin:
        #     responsetext = fin.read()
        if response.status_code == 404:
            return {"pid": pid, "success": 1,"project_link":"","project_id":""}
        if failure_reason:
            return {
                "pid": pid, "success": 0, "failure_reason": failure_reason,
                "status_code": response.status_code,
            }


        raelproject_url=project_url
        if response.status_code==200:
            # with open("user_agent.txt", "a", encoding="utf-8") as fout:
            #     fout.write(user_agent_item+"\n")

            realproject_url=response.url


            responsetext=response.text
            current_project = re.search(r'window.current_project = (.+?);\n', responsetext, re.M | re.S)
            if current_project is None:
                return {
                    "pid": pid, "success": 0,
                    "failure_reason": "project_data_not_found",
                    "status_code": response.status_code,
                }
            current_projectstr = current_project.group(1)
            new_current_projectstr=literal_eval(current_projectstr)
            new_current_projectstr=html.unescape(new_current_projectstr)



            # with open("project.json", "w", encoding="utf-8") as fout:
            #     fout.write(new_current_projectstr)
            current_projectjson=json.loads(new_current_projectstr)

            project_id=""
            project_title=""
            currency=""
            target_money=""
            already_money=""
            desc_text=""
            update_num=0
            comments_num=0
            question_num=0
            start_time=None
            end_time=None
            last_update=None
            duration=""
            support_num=0
            new_support_num=0
            existing_support_num=0
            category=""
            subcategory=""
            location=""
            status=""

            title_page_video_url=""
            title_page_image_url=""

            country_code=""
            country_name=""
            campaign_tags=""
            staff_pick=0
            fundraising_progress=""




            project_id=current_projectjson["id"]
            project_title=current_projectjson["name"]
            if "currency" in current_projectjson:
               currency=current_projectjson["currency"]
            if "goal" in current_projectjson:
               target_money=current_projectjson["goal"]

            if "pledged" in current_projectjson:
               already_money=current_projectjson["pledged"]
               falready_money=float(already_money)
               ftarget_money=float(target_money)
               if ftarget_money!=0:
                  ffundraising_progress=round(falready_money/ftarget_money*100)
                  fundraising_progress=str(ffundraising_progress)+"%"




            if "staff_pick" in current_projectjson and current_projectjson["staff_pick"]:
                staff_pick=1

            # if "tags" in current_projectjson and current_projectjson["tags"]:
            #    raise Exception("该项目存在标签")


            if "updates_count" in current_projectjson:
               update_num=int(current_projectjson["updates_count"])

            if "comments_count" in current_projectjson:
               comments_num=int(current_projectjson["comments_count"])

            if "backers_count" in current_projectjson:
               support_num=int(current_projectjson["backers_count"])

            if "launched_at" in current_projectjson and current_projectjson["launched_at"]:
                start_time_stamp=current_projectjson["launched_at"]
                start_time_dt=datetime.datetime.fromtimestamp(start_time_stamp)
                start_time = start_time_dt.strftime('%Y-%m-%d')


                if "deadline" in current_projectjson and current_projectjson["deadline"]:
                    end_time_stamp=current_projectjson["deadline"]
                    end_time_dt=datetime.datetime.fromtimestamp(end_time_stamp)
                    end_time = end_time_dt.strftime('%Y-%m-%d')
                    duration = (end_time_dt-start_time_dt).days



            if "updated_at" in current_projectjson and current_projectjson["updated_at"]:
                last_update_stamp=current_projectjson["updated_at"]
                last_update_dt=datetime.datetime.fromtimestamp(last_update_stamp)
                last_update = last_update_dt.strftime('%Y-%m-%d')



            if "location" in current_projectjson and current_projectjson["location"]:
                if "displayable_name" in  current_projectjson["location"]:
                   location=current_projectjson["location"]["displayable_name"]
                if "country" in  current_projectjson["location"]:
                   country_code =current_projectjson["location"]["country"]
                if "expanded_country" in current_projectjson["location"]:
                       country_name = current_projectjson["location"]["expanded_country"]


            if "state" in current_projectjson:
                status=current_projectjson["state"]

            if "category" in current_projectjson and current_projectjson["category"]:
                if "parent_name" in current_projectjson["category"]:
                   category = current_projectjson["category"]["parent_name"]
                   if "name" in current_projectjson["category"]:
                       subcategory=current_projectjson["category"]["name"]
                else:
                    if "name" in current_projectjson["category"]:
                        category = current_projectjson["category"]["name"]
                        subcategory=""


            if "profile" in current_projectjson:
                if "blurb" in current_projectjson["profile"] and current_projectjson["profile"]["blurb"]:
                  desc_text=current_projectjson["profile"]["blurb"]
                elif "blurb" in current_projectjson:
                  desc_text = current_projectjson["blurb"]




            if "video" in current_projectjson and current_projectjson["video"]:
                if "base" in current_projectjson["video"]:
                   title_page_video_url = current_projectjson["video"]["base"]

            if "photo" in current_projectjson and current_projectjson["photo"] :
                if "1536x864" in current_projectjson["photo"]:
                    title_page_image_url=current_projectjson["photo"]["1536x864"]


            htmlpage = etree.HTML(responsetext)
            question_numnode=htmlpage.xpath('//*[@id="faq-emoji"]/@emoji-data')
            if question_numnode:
                 question_num=int(question_numnode[0])


            creator_id=""

            if "creator" in current_projectjson and current_projectjson["creator"]:
                if "id" in current_projectjson["creator"]:
                   creator_id=current_projectjson["creator"]["id"]






            maininfo={
                "pid":pid,
                "project_id":project_id,
                "project_link":realproject_url,
                "title": project_title,
                "currency":currency,
                "target_money":target_money,
                "already_money":already_money,
                "desc_text":desc_text,
                "update_num":update_num,
                "reviews_num":comments_num,
                "question_num":question_num,
                "start_time":start_time,
                "end_time":end_time,
                "last_update":last_update,
                "duration":duration,
                "support_num":support_num,
                "new_support_num":new_support_num,
                "existing_support_num":existing_support_num,
                "category":category,
                "subcategory":subcategory,
                "location":location,
                "country_code":country_code,
                "country_name":country_name,
                "project_status":status,
                "staff_pick":staff_pick,
                "fundraising_progress":fundraising_progress,
                "title_page_video_url":title_page_video_url,
                "title_page_image_url":title_page_image_url,
                "creator_id":creator_id,

            }
            resultdata["maininfo"] = maininfo
            resultdata["project_id"] = project_id
            resultdata["project_link"] = realproject_url
            resultdata["success"] = 1

    except Exception as e:
        print("报错:", project_url,str(e))
        resultdata={
            "pid": pid, "success": 0, "failure_reason": str(e),
            "status_code": None,
        }

    return resultdata
def downloadmaininfo(limit=50):
    for _ in range(1):

        db = get_mysqldb()
        if db is None:
            print("数据库不可用，本轮停止；请先启动 MySQL 后重试。", flush=True)
            return False
        cursor = db.cursor()



        begin_postion=0

        end_postion=1000000

        querysql = """
              select pid,project_url from crawling_url where pid >=%s AND pid<%s AND main =0 LIMIT %s
               """%(begin_postion,end_postion,int(limit))

        cursor.execute(querysql)  # 执行SQL语句
        scrapy_urls = cursor.fetchall()
        db.close()

        if len(scrapy_urls) ==0:
              break

        else:
            try:
                db = get_mysqldb()
                if db is None:
                    print("数据库不可用，本轮停止。", flush=True)
                    return False
                with ThreadPoolExecutor(max_workers=Max_works) as t1:

                    obj_list1 = []
                    for scrapy_url in scrapy_urls:
                        obj_list1.append(t1.submit(get_mainpage,scrapy_url))
                        if Max_works == 1 and REQUEST_DELAY_SECONDS:
                            time.sleep(REQUEST_DELAY_SECONDS)

                    success_count = 0
                    failure_count = 0
                    for future in as_completed(obj_list1):
                         retrunrewards = future.result()

                         if retrunrewards["success"]==1:
                             try:
                                 cursor = db.cursor()
                                 link_pid = retrunrewards["pid"]
                                 if "maininfo" in retrunrewards and retrunrewards["maininfo"]:
                                     maininfo=retrunrewards["maininfo"]

                                     insertmaininfosql = """ insert into main_info(pid,project_id,project_link,title,currency,
                                                                                   target_money,already_money,desc_text,update_num,reviews_num,
                                                                                   question_num,start_time,end_time,last_update,duration,
                                                                                   support_num,new_support_num,existing_support_num,category,subcategory,
                                                                                   location,country_code,country_name,project_status,staff_pick,
                                                                                   fundraising_progress,title_page_video_url,title_page_image_url,creator_id) 
                                                                               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) 
                                      """
                                     insertmaininfodata=[(maininfo["pid"],maininfo["project_id"],maininfo["project_link"],maininfo["title"],maininfo["currency"],
                                             maininfo["target_money"], maininfo["already_money"],maininfo["desc_text"], maininfo["update_num"],maininfo["reviews_num"],
                                             maininfo["question_num"], maininfo["start_time"],maininfo["end_time"], maininfo["last_update"],maininfo["duration"],
                                             maininfo["support_num"], maininfo["new_support_num"],maininfo["existing_support_num"], maininfo["category"],maininfo["subcategory"],
                                             maininfo["location"], maininfo["country_code"],maininfo["country_name"], maininfo["project_status"],maininfo["staff_pick"],
                                             maininfo["fundraising_progress"], maininfo["title_page_video_url"],maininfo["title_page_image_url"], maininfo["creator_id"]
                                             )]

                                     cursor.executemany(insertmaininfosql,insertmaininfodata)  # 执行SQL语句
                                     # if maininfo["title_page_image_url"]:
                                     #     insertimage_infosql = """ insert into image_info(pid,project_id,project_link,part_of,row_num,image_url,image_title)
                                     #                             VALUES(%s,%s,%s,%s,%s,%s,%s) """
                                     #
                                     #
                                     #     insertimage_infos=[(maininfo["pid"], maininfo["project_id"],maininfo["project_link"], "header",1, maininfo["title_page_image_url"],"")]
                                     #
                                     #     cursor.executemany(insertimage_infosql, insertimage_infos)
                                     # if maininfo["title_page_video_url"]:
                                     #     insertimage_infosql2 = """ insert into video_info(pid,project_id,project_link,part_of,row_num,video_url)
                                     #                             VALUES(%s,%s,%s,%s,%s,%s) """
                                     #
                                     #     insertimage_infos2=[(maininfo["pid"], maininfo["project_id"],maininfo["project_link"], "header",1, maininfo["title_page_video_url"])]
                                     #
                                     #     cursor.executemany(insertimage_infosql2, insertimage_infos2)

                                 cursor.execute(
                                     "update crawling_url set main=1,real_project_url=%s,project_id=%s where pid=%s",
                                     (retrunrewards["project_link"], retrunrewards["project_id"], link_pid),
                                 )
                                 db.commit()  # 提交
                                 success_count += 1
                                 print("main_info下载成功!")

                             except Exception as e:
                                 print(str(e))
                                 db.rollback()  # 如果执行失败要回滚
                         else:
                             failure_count += 1
                             print(
                                 "任务失败，保留待重试: "
                                 f"pid={retrunrewards.get('pid')} "
                                 f"status={retrunrewards.get('status_code')} "
                                 f"reason={retrunrewards.get('failure_reason')}",
                                 flush=True,
                             )
                    print(f"本轮完成: 成功 {success_count}，失败 {failure_count}", flush=True)

            finally:
                if db is not None:
                    db.close()
    return True
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
        return None
def get_proxy(type):

    if type==0:
        proxies = {}
    elif type==1:
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
def get_requests_param():
    expiration=False
    while True:
        impersonate_item=random.choice(impersonate_list)
        user_agent_item = random.choice(user_agent_list)
        headers=global_headers.copy()
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
        except Exception as e:
            print("连接代理服务器失败")
            time.sleep(2)

    return expiration

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Kickstarter 项目主页采集")
    parser.add_argument("--url", help="只测试一个项目 URL，不连接数据库")
    parser.add_argument("--limit", type=int, default=50, help="数据库模式本轮最多处理数")
    args = parser.parse_args()

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
                        "chrome116", "chrome119", "chrome120", "safari15_3", "safari15_5", "safari17_0", "safari17_2_ios","chrome99_android"]



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

    # TLS 指纹和 User-Agent 必须匹配，并在一次运行中保持不变。
    FIXED_IMPERSONATE = "chrome124"
    FIXED_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


    global_cookies = {'lang': 'en'}


    global_headers = {
        'authority': 'www.kickstarter.com',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'zh-CN,zh;q=0.9',
        'cache-control': 'max-age=0',
    }

    Use_proxy=proxy_enable_proxy
    Max_works=max_threads

    # aaa=get_mainpage({"pid":99,"project_url":"https://www.kickstarter.com/projects/deviever/dub-step-the-dub-step-guitar-pedal"})
    # abc=json.dumps(aaa)
    # with open("page.json", "w", encoding="utf-8") as fout:
    #     fout.write(abc)
    # print(abc)

    if args.url:
        test_result = get_mainpage({"pid": 0, "project_url": args.url})
        print(json.dumps(test_result, ensure_ascii=False, default=str))
        raise SystemExit(0 if test_result.get("success") else 2)

    raise SystemExit(0 if downloadmaininfo(limit=max(1, args.limit)) else 3)

