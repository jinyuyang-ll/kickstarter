import lxml.html
from curl_cffi import requests as cffirequests
import re
import json
from lxml import etree
import html
import datetime
from bs4 import BeautifulSoup
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import pymysql
import time


def quotedStr(strtext):
    strtext = str(strtext)
    return "\"" + strtext + "\""


def get_proxy(type):
    if type == 1:

        proxy_host = random.choice(proxy_proxy_host_list)
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


def get_community(project_info):

    pid = project_info["pid"]
    project_url = project_info["project_url"]
    project_id = project_info["project_id"]
    resultdata = {"pid": pid, "success": 0, "project_link": project_url, "project_id": project_id}
    try:
        communityurl_old = project_url.split("?", 1)[0]
        communityurl=communityurl_old+"/community"

        impersonate_item = random.choice(impersonate_list)
        user_agent_item = random.choice(user_agent_list)
        headers=global_headers.copy()
        headers["referer"]=communityurl_old
        headers["user-agent"] = user_agent_item

        proxiesip = get_proxy(Use_proxy)
        response = cffirequests.get(
            communityurl,
            cookies=global_cookies,
            headers=headers,
            impersonate=impersonate_item,
            proxies=proxiesip
        )


        if response.status_code==404:
            return {"pid": pid, "success": 1, "project_link": "", "project_id": ""}

        if response.status_code==403:
            return {"pid": pid, "success": 2}
        if response.status_code==200:
            responsetext=response.text
            htmlpage = etree.HTML(responsetext)

            new_backers="0"
            returning_backers="0"
            top_cities_list=[]
            top_country_list=[]

            NS_projects__community_section=htmlpage.xpath('//div[@class="NS_projects__community_section"]//text()')

            if NS_projects__community_section is None:
                return {"pid": pid, "success": 1, "project_link": project_url, "project_id": project_id}


            new_backers_node=htmlpage.xpath('//div[@class="new-backers"]/div/text()')
            if new_backers_node:
                new_backers=str(new_backers_node[0])
                new_backers=new_backers.strip()
                new_backers = re.sub(r'\D', "", new_backers)

            returning_backers_node=htmlpage.xpath('//div[@class="existing-backers"]/div/text()')
            if returning_backers_node:
                returning_backers=str(returning_backers_node[0])
                returning_backers=returning_backers.strip()
                returning_backers = re.sub(r'\D', "", returning_backers)

            top_cities_nodes=htmlpage.xpath('//div[@class="community-section__locations_cities"]//div[contains(@class,"location-list__item")]')
            country1rownum=0
            for top_cities_nd in top_cities_nodes:
                country=""
                city=""
                backer_num="0"
                country1rownum+=1
                country_node=top_cities_nd.xpath('./div[@class="left"]/div[contains(@class,"secondary-text")]//text()')
                if country_node:
                   for country_nd in country_node:
                       tempcountry_nd=str(country_nd)
                       tempcountry_nd=tempcountry_nd.strip()
                       if tempcountry_nd!="":
                          country+=tempcountry_nd

                city_node=top_cities_nd.xpath('./div[@class="left"]/div[contains(@class,"primary-text")]//text()')
                if city_node:
                   for city_nd in city_node:
                       tempcity_nd=str(city_nd)
                       tempcity_nd=tempcity_nd.strip()
                       if tempcity_nd!="":
                          city+=tempcity_nd


                backer_num_node=top_cities_nd.xpath('./div[@class="right"]//text()')
                if city_node:
                   backer_num_text_temp=""
                   for backer_num_nd in backer_num_node:
                       tempbacker_num_nd=str(backer_num_nd)
                       tempbacker_num_nd=tempbacker_num_nd.strip()
                       if tempbacker_num_nd!="":
                          backer_num_text_temp+=tempbacker_num_nd

                   backer_num=re.sub(r'\D', "", backer_num_text_temp)


                top_cities_list.append({"row_num":country1rownum,"country":country,"city":city,"backer_num":backer_num})


            top_country_nodes=htmlpage.xpath('//div[@class="community-section__locations_countries"]//div[contains(@class,"location-list__item")]')
            country2rownum=0
            for top_country_nd in top_country_nodes:
                country2=""
                backer_num2="0"
                country2rownum+=1
                country_node2=top_country_nd.xpath('./div[@class="left"]//text()')
                if country_node2:
                   for country_nd2 in country_node2:
                       tempcountry_nd2=str(country_nd2)
                       tempcountry_nd2=tempcountry_nd2.strip()
                       if tempcountry_nd2!="":
                          country2+=tempcountry_nd2


                backer_num_node2=top_country_nd.xpath('./div[@class="right"]//text()')
                if backer_num_node2:
                   backer_num_text_temp2=""
                   for backer_num_nd2 in backer_num_node2:
                       tempbacker_num_nd2=str(backer_num_nd2)
                       tempbacker_num_nd2=tempbacker_num_nd2.strip()
                       if tempbacker_num_nd2!="":
                          backer_num_text_temp2+=tempbacker_num_nd2

                   backer_num2=re.sub(r'\D', "", backer_num_text_temp2)


                top_country_list.append({"row_num":country2rownum,"country":country2,"backer_num":backer_num2})

            communitydcit={
               "new_support_num":new_backers,
               "existing_support_num":returning_backers,
               "top_cities":top_cities_list,
               "top_country": top_country_list
            }
            resultdata["communityinfo"] = communitydcit
            resultdata["success"] = 1

    except Exception as e:
        print("报错:", project_url, str(e))
        resultdata = {"pid": pid, "success": 0}

    return resultdata


def downloadmacommunity():
    while True:

        db = get_mysqldb()
        cursor = db.cursor()

        begin_postion=0
        end_postion=1000000


        querysql = """
              select pid,project_url,project_id from crawling_url where pid >=%s AND pid<%s AND community =0 LIMIT 2000
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
                        obj_list1.append(t1.submit(get_community,scrapy_url))

                    for future in as_completed(obj_list1):
                         retrunrewards = future.result()


                         if retrunrewards["success"]==1:
                             try:
                                 cursor = db.cursor()
                                 link_pid = retrunrewards["pid"]
                                 if "communityinfo" in retrunrewards and retrunrewards["communityinfo"]:
                                     communityinfo=retrunrewards["communityinfo"]
                                     top_cities=communityinfo["top_cities"]
                                     if top_cities:
                                         inserttop_citiessql = """ insert into community_city(pid,row_num,project_id,backer_num,project_link,country,city) 
                                                                 VALUES(%s,%s,%s,%s,%s,%s,%s) """
                                         inserttop_cities = []
                                         for datas in top_cities:
                                             inserttop_cities.append((retrunrewards["pid"],datas["row_num"],retrunrewards["project_id"],datas["backer_num"],retrunrewards["project_link"],datas["country"],datas["city"]))

                                         cursor.executemany(inserttop_citiessql,inserttop_cities)

                                     top_country=communityinfo["top_country"]
                                     if top_country:
                                         inserttop_countrysql = """ insert into community_country(pid,row_num,project_id,backer_num,project_link,country) 
                                                                 VALUES(%s,%s,%s,%s,%s,%s) """
                                         inserttop_country = []
                                         for datas in top_country:
                                             inserttop_country.append((retrunrewards["pid"],datas["row_num"],retrunrewards["project_id"],datas["backer_num"],retrunrewards["project_link"],datas["country"]))

                                         cursor.executemany(inserttop_countrysql,inserttop_country)



                                     updatesql = """update main_info  set new_support_num=%s,existing_support_num=%s where pid=%s """ % (communityinfo["new_support_num"],communityinfo["existing_support_num"],link_pid)
                                     cursor.execute(updatesql)

                                 updatesql = """update crawling_url set community=1 where pid=%s """%link_pid
                                 cursor.execute(updatesql)
                                 db.commit()  # 提交
                                 print("community下载成功!")

                             except Exception as e:
                                 print(str(e))
                                 db.rollback()  # 如果执行失败要回滚

            finally:
                db.close()

def get_mysqldb():
    try:

        db = pymysql.connect(host=db_host,
                             port=db_port,
                             user=db_user,
                             password=db_password,
                             database=db_database,
                             charset="utf8mb4",
                             connect_timeout=60,
                             cursorclass=pymysql.cursors.DictCursor)
        # print("数据库连接成功")
        return db
    except Exception as e:
        print("数据库连接失败:", str(e))


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

                # if response_time > expiration_time:
                #     expiration=True
                # else:
                #     expiration=False

                break;
            else:
                print("访问网站失败",response.status_code)
        except Exception as e:
            print("连接代理服务器失败")
            time.sleep(2)

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
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'zh-CN,zh;q=0.9',
        'cache-control': 'max-age=0',
    }

    Use_proxy=proxy_enable_proxy
    Max_works=max_threads


    # aaa=get_community({"pid":1,"project_id":2,"project_url":"https://www.kickstarter.com/projects/trickortreatstudios/la-1-a-cyber-noir-detective-game"})
    # abc=json.dumps(aaa)
    # print(abc)

    downloadmacommunity()


