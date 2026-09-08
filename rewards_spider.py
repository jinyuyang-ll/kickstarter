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

def get_Rewards(project_info):

    pid=project_info["pid"]
    project_url=project_info["project_url"]
    project_id = project_info["project_id"]

    resultdata = {"pid": pid, "success": 0, "project_link": project_url, "project_id": project_id}

    try:
        url=project_url.split("?", 1)[0]
        slugs = re.search(r'com/projects/(.+)', url)
        if slugs:
           slug = slugs.group(1)
        else:
            return {"pid": pid, "success": 1}

        impersonate_item = random.choice(impersonate_list)
        user_agent_item = random.choice(user_agent_list)
        headers=global_headers.copy()
        headers["x-csrf-token"]=global_param["csrf_token"]
        headers["referer"]=project_url
        headers["user-agent"] = user_agent_item
        cookies=global_cookies.copy()
        cookies["_ksr_session"]=global_param["session"]


        json_data = {
            'query': '\n  query RewardsTab($slug: String!) {\n    usdType\n    me {\n      id\n      isCreator\n      chosenCurrency\n      location {\n        id\n        country\n        countryName\n      }\n    }\n    project(slug: $slug) {\n      state\n      id\n      name\n      fxRate\n      minPledge\n      creator {\n        id\n      }\n      currency\n      isUserCreator\n      isInPostCampaignPledgingPhase\n      backing {\n        id\n        reward {\n          id\n        }\n        backingDetailsPageUrl: backingDetailsPageRoute(type: path, tab: details)\n      }\n      actions {\n        displayConvertAmount\n      }\n      isLaunched\n      rewards {\n        nodes {\n          id\n          name\n          audienceData { secret }\n          convertedAmount { amount currency }\n          amount { amount currency symbol }\n          available\n          items {\n            edges {\n              quantity\n              node {\n                id\n                name\n                image {\n                  id\n                  url(width: 600)\n                  altText\n                }\n              }\n            }\n          }\n          displayableAddons {\n            nodes {\n              id\n              name\n              description\n              convertedAmount { amount currency }\n              image {\n                id\n                url(width: 600)\n                altText\n              }\n            }\n          }\n          description\n          estimatedDeliveryOn\n          backersCount\n          backerImages(limit: 3) {\n            id\n            url(width: 120)\n            altText\n          }\n          backerReportUrl\n          image {\n            id\n            url(width: 600)\n            altText\n          }\n          shippingEnabled\n          shippingPreference\n          shippingSummary\n          endsAt\n          limit\n          remainingQuantity\n          featured\n        }\n      }\n    }\n  }\n',
            'variables': {
                'slug': slug,
            },
        }

        proxiesip = get_proxy(Use_proxy)

        response = cffirequests.post('https://www.kickstarter.com/graph',cookies=cookies, headers=headers, json=json_data,impersonate=impersonate_item,proxies=proxiesip)




        response.encoding="utf-8"
        #
        # with open("Rewards.json", "w", encoding="utf-8") as fout:
        #     fout.write(response.text)
        #
        # with open("Rewards.json", "r", encoding="utf-8") as fin:
        #     responsetext = fin.read()



        if response.status_code==200:
            responsetext=response.text
            jsondata=json.loads(responsetext)
            project_data=jsondata["data"]["project"]
            if project_data is None:
                return {"pid": pid, "success": 1,"project_link":project_url,"project_id":project_id }

            if project_data:
                alldata_list=[]
                rewards_nodes = project_data["rewards"]["nodes"]
                if rewards_nodes:
                    rownum=0
                    for rewards_node in rewards_nodes:
                        rownum+=1
                        rewards_id_en=str(rewards_node["id"])
                        rewards_id_en="Reward-"+rewards_id_en
                        rewards_id = str(base64.b64encode(rewards_id_en.encode('utf8')), encoding='utf8')

                        real_roject_id_en = str(project_data["id"])
                        real_roject_id_str = base64.b64decode(real_roject_id_en).decode('utf-8')
                        real_roject_id = real_roject_id_str.split("-", 1)[1]
                        backers="0"
                        price="0"
                        currency=""
                        currency_symbol=""
                        estimated_delivery=""
                        title=""
                        ships_to=""
                        desc_text=""
                        limited_quantity_total=""
                        limited_quantity_left=""
                        existing_image=0
                        existing_add_on_rewards=0
                        contain_item_num=0
                        item_included=""
                        add_on_rewards=""
                        top3_image=""
                        menu_image=""

                        if rewards_node["name"]:
                           title=rewards_node["name"]


                        if rewards_node["backersCount"]:
                           backers=rewards_node["backersCount"]


                        if rewards_node["amount"]["amount"]:
                           price=rewards_node["amount"]["amount"]
                           currency=rewards_node["amount"]["currency"]
                           currency_symbol=rewards_node["amount"]["symbol"]


                        if rewards_node["estimatedDeliveryOn"]:
                           estimated_delivery=rewards_node["estimatedDeliveryOn"]

                        if rewards_node["shippingSummary"]:
                           ships_to=rewards_node["shippingSummary"]

                        if rewards_node["description"]:
                           desc_text=rewards_node["description"]

                        if rewards_node["limit"]:
                           limited_quantity_total=rewards_node["limit"]

                        if rewards_node["remainingQuantity"]:
                           limited_quantity_left=rewards_node["remainingQuantity"]

                        if rewards_node["image"]:
                           menu_image=rewards_node["image"]["url"]
                           existing_image=1

                        if rewards_node["items"]:
                           tmepitem_included_lists=rewards_node["items"]["edges"]
                           contain_item_num=len(tmepitem_included_lists)
                           item_included_lists=[]
                           for tempitem_included_li in tmepitem_included_lists:
                               item_included_lists.append({"name":tempitem_included_li["node"]["name"],"quantity":tempitem_included_li["quantity"]})

                           if item_included_lists:
                              item_included = json.dumps(item_included_lists)


                        if rewards_node["displayableAddons"]:
                           displayableAddons=rewards_node["displayableAddons"]["nodes"]
                           if displayableAddons:
                               existing_add_on_rewards=1
                               add_on_rewards_list=[]
                               for displayableAddon in displayableAddons:
                                   add_on_rewards_name=displayableAddon["name"]
                                   add_on_rewards_description=displayableAddon["description"]
                                   add_on_rewards_amount = displayableAddon["convertedAmount"]["amount"]
                                   add_on_rewards_image_url=""
                                   if displayableAddon["image"]:
                                       add_on_rewards_image_url=displayableAddon["image"]["url"]
                                   add_on_rewards_list.append({"name":add_on_rewards_name,"description":add_on_rewards_description,"amount":add_on_rewards_amount,"image_url":add_on_rewards_image_url})

                               if add_on_rewards_list:
                                  add_on_rewards = json.dumps(add_on_rewards_list)


                        if rewards_node["backerImages"]:
                           backerImages=rewards_node["backerImages"]
                           backerImages_list=[]
                           for backerImage in backerImages:
                               backerImages_list.append(backerImage["url"])

                           if backerImages_list:
                              top3_image = json.dumps(backerImages_list)

                        alldata_list.append({
                        "pid":pid,
                        "rownum": rownum,
                        "project_id":real_roject_id,
                        "project_link":project_url,
                        "rewards_id":rewards_id,
                        "title":title,
                        "backers":backers,
                        "currency":currency,
                        # "currency_symbol":currency_symbol,
                        "price":price,
                        "estimated_delivery":estimated_delivery,
                        "ships_to":ships_to,
                        "desc_text":desc_text,
                        "limited_quantity_total":limited_quantity_total,
                        "limited_quantity_left":limited_quantity_left,
                        # "existing_image":existing_image,
                        # "existing_add_on_rewards":existing_add_on_rewards,
                        # "contain_item_num":contain_item_num,
                        # "item_included":item_included,
                        # "add_on_rewards":add_on_rewards,
                        # "top3_image":top3_image,
                        # "menu_image":menu_image
                        })

                    resultdata["datalist"]=alldata_list
                    resultdata["success"]=1
                else:
                    return {"pid": pid, "success": 1, "project_link": project_url, "project_id": project_id}

    except Exception as e:
        # print("报错:", project_url,str(e))
        resultdata={"pid": pid, "success": 0}


    return resultdata

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

def downloadrewards():
    retry_number=0
    while True:
        db = get_mysqldb()
        cursor = db.cursor()


        begin_postion=0
        end_postion=1000000

        querysql = """
              select pid,project_id,project_url from crawling_url where pid >=%s AND pid<%s AND rewards =0 LIMIT 2000
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
                        obj_list1.append(t1.submit(get_Rewards,scrapy_url))

                    for future in as_completed(obj_list1):
                         retrunrewards = future.result()

                         if retrunrewards["success"]==1:
                             try:

                                 cursor = db.cursor()
                                 link_pid = retrunrewards["pid"]
                                 if "datalist" in retrunrewards and  retrunrewards["datalist"]:
                                       all_datas=retrunrewards["datalist"]

                                       insertimage_infosql = """ insert into rewards_info(pid,rownum,project_id,project_link,rewards_id,
                                                                                        title,backers,currency,price,estimated_delivery,
                                                                                        limited_quantity_total,limited_quantity_left,ships_to,desc_text)
                                                               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) """
                                       insertimage_infos = []
                                       for datas in all_datas:
                                           insertimage_infos.append((datas["pid"], datas["rownum"], datas["project_id"], datas["project_link"], datas["rewards_id"],
                                                                     datas["title"], datas["backers"], datas["currency"], datas["price"], datas["estimated_delivery"],
                                                                     datas["limited_quantity_total"], datas["limited_quantity_left"],datas["ships_to"], datas["desc_text"]
                                                                     ))

                                       cursor.executemany(insertimage_infosql, insertimage_infos)


                                 updatesql = """update crawling_url set rewards=1 where pid=%s """ %link_pid
                                 cursor.execute(updatesql)
                                 db.commit()  # 提交
                                 print("Rewards下载成功!")

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
    # aaa=get_Rewards({"pid":99,"project_id":"1998400303", "project_url":"https://www.kickstarter.com/projects/tadcalo/tadcalo-full-switch-two-type-c-kvm-docking-station"})
    # abc=json.dumps(aaa)
    # with open("page.json", "w", encoding="utf-8") as fout:
    #     fout.write(abc)
    downloadrewards()


