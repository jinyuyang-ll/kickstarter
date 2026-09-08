import lxml.html
from curl_cffi import requests as cffirequests
import re
import json
from lxml import etree
import html
import datetime
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

def get_Comments(project_info):
    pid = project_info["pid"]
    project_url = project_info["project_url"]
    project_id = project_info["project_id"]
    comments_cursor = project_info["comments_cursor"]

    if str(comments_cursor)=="":
        comments_cursor=None

    resultdata = {"pid": pid, "success": 0, "project_link": project_url, "project_id": project_id}

    try:
        commentsurl = project_url.split("?", 1)[0]
        commentsurl = commentsurl + "/comments"
        commentableIdstr="Project-"+str(project_id)
        commentableId=str(base64.b64encode(commentableIdstr.encode('utf8')), encoding='utf8')

        impersonate_item = random.choice(impersonate_list)
        user_agent_item = random.choice(user_agent_list)
        headers = global_headers.copy()
        headers["x-csrf-token"] = global_param["csrf_token"]
        headers["referer"] = commentsurl
        headers["user-agent"] =user_agent_item
        cookies = global_cookies.copy()
        cookies["_ksr_session"] = global_param["session"]

        json_data = [
            {
                'operationName': 'CommentsQuery',
                'variables': {
                    'commentableId': commentableId,
                    'nextCursor': comments_cursor,
                    'previousCursor': None,
                    'replyCursor': None,
                    'first': 25,
                    'last': None,
                },
                'query': 'query CommentsQuery($commentableId: ID!, $nextCursor: String, $previousCursor: String, $replyCursor: String, $first: Int, $last: Int) {\n  commentable: node(id: $commentableId) {\n    id\n    ... on Project {\n      url\n      __typename\n    }\n    ... on Commentable {\n      canComment\n      canCommentSansRestrictions\n      commentsCount\n      projectRelayId\n      canUserRequestUpdate\n      comments(first: $first, last: $last, after: $nextCursor, before: $previousCursor) {\n        edges {\n          node {\n            ...CommentInfo\n            ...CommentReplies\n            __typename\n          }\n          __typename\n        }\n        pageInfo {\n          startCursor\n          hasNextPage\n          hasPreviousPage\n          endCursor\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  me {\n    id\n    name\n    imageUrl(width: 200)\n    isKsrAdmin\n    url\n    userRestrictions {\n      restriction\n      releaseAt\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment CommentInfo on Comment {\n  id\n  body\n  createdAt\n  parentId\n  author {\n    id\n    imageUrl(width: 200)\n    name\n    url\n    __typename\n  }\n  removedPerGuidelines\n  authorBadges\n  canReport\n  canDelete\n  canPin\n  hasFlaggings\n  deletedAuthor\n  deleted\n  sustained\n  pinnedAt\n  authorCanceledPledge\n  authorBacking {\n    backingUrl\n    id\n    __typename\n  }\n  __typename\n}\n\nfragment CommentReplies on Comment {\n  replies(last: 25, before: $replyCursor) {\n    totalCount\n    nodes {\n      ...CommentInfo\n      __typename\n    }\n    pageInfo {\n      startCursor\n      hasPreviousPage\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n',
            },
        ]
        proxiesip = get_proxy(Use_proxy)
        response = cffirequests.post('https://www.kickstarter.com/graph', cookies=cookies, headers=headers, json=json_data, impersonate=impersonate_item,proxies=proxiesip)

        if response.status_code == 200:

            # with open("comments.json", "w", encoding="utf-8") as fout:
            #     fout.write(response.text)
            comments_finish=1
            comments_cursor=""
            responsetext = response.text
            jsondata = json.loads(responsetext)

            project_data = jsondata[0]["data"]["commentable"]
            if project_data is None:
                 return {"pid": pid, "success": 1, "project_link": project_url, "project_id": project_id,"comments_finish":1,"comments_cursor":""}

            commentlist=[]
            if project_data["comments"]["edges"]:
                commentsedgeslist=project_data["comments"]["edges"]
                if commentsedgeslist:
                    for commentsedges in commentsedgeslist:
                        if commentsedges["node"]:
                            comments_id=""
                            creator_id=""
                            author_name=""
                            author_tag=""
                            pub_time=""
                            pub_time_stamp=0
                            body=""
                            is_add_on=0
                            comments_image=""
                            parent_comments_id=""
                            replies_nums=0
                            replies_cursor=""
                            replies_finish=0

                            comments_id=commentsedges["node"]["id"]
                            if "author" in commentsedges["node"] and commentsedges["node"]["author"]:

                               creator_id_en = str(commentsedges["node"]["author"]["id"])
                               creator_id_str = base64.b64decode(creator_id_en).decode('utf-8')
                               creator_id = creator_id_str.split("-", 1)[1]
                               author_name=commentsedges["node"]["author"]["name"]
                               comments_image = commentsedges["node"]["author"]["imageUrl"]

                            if "authorBadges" in commentsedges["node"] and commentsedges["node"]["authorBadges"]:
                                author_tag_list=commentsedges["node"]["authorBadges"]
                                author_tag=",".join(author_tag_list)

                            if "createdAt" in commentsedges["node"] and commentsedges["node"]["createdAt"]:
                                pub_time_stamp=commentsedges["node"]["createdAt"]
                                pub_time_dt = datetime.datetime.fromtimestamp(pub_time_stamp)
                                pub_time = pub_time_dt.strftime('%Y-%m-%d %H:%M:%S')

                            if "body" in commentsedges["node"] and commentsedges["node"]["body"]:
                                body=commentsedges["node"]["body"]

                            if "replies" in commentsedges["node"] and commentsedges["node"]["replies"]:
                                if commentsedges["node"]["replies"]["nodes"]:
                                    is_add_on=1
                                else:
                                    is_add_on=0

                                replies_nums=commentsedges["node"]["replies"]["totalCount"]

                                if commentsedges["node"]["replies"]["pageInfo"]:
                                    repliespages=commentsedges["node"]["replies"]["pageInfo"]
                                    if repliespages:
                                        if commentsedges["node"]["replies"]["pageInfo"]["startCursor"]:
                                            replies_cursor=commentsedges["node"]["replies"]["pageInfo"]["startCursor"]
                                        if commentsedges["node"]["replies"]["pageInfo"]["hasPreviousPage"]:
                                            replies_finish=0
                                        else:
                                            replies_finish=1

                            commentlist.append({
                                "comments_type": "review",
                                "comments_id":comments_id,
                                "creator_id":creator_id,
                                "author_name":author_name,
                                "author_tag":author_tag,
                                "pub_time":pub_time,
                                "pub_time_stamp":pub_time_stamp,
                                "body":body,
                                "is_add_on":is_add_on,
                                "comments_image":comments_image,
                                "parent_comments_id":"",
                                "replies_nums":replies_nums,
                                "replies_cursor":replies_cursor,
                                "replies_finish":replies_finish
                            })

                            if "replies" in commentsedges["node"] and commentsedges["node"]["replies"]:
                                if commentsedges["node"]["replies"]["nodes"]:
                                    subcommentsedgesnodes=commentsedges["node"]["replies"]["nodes"]
                                    for subcommentsedges in subcommentsedgesnodes:
                                        if subcommentsedges:
                                            creator_id=""
                                            author_name = ""
                                            author_tag = ""
                                            pub_time = ""
                                            pub_time_stamp = 0
                                            body = ""
                                            is_add_on = 0
                                            comments_image = ""
                                            parent_comments_id = ""
                                            replies_nums = 0
                                            replies_cursor = ""
                                            replies_finish = 0

                                            subcomments_id = subcommentsedges["id"]
                                            if "author" in subcommentsedges and subcommentsedges["author"]:
                                                creator_id_en = str(subcommentsedges["author"]["id"])
                                                creator_id_str = base64.b64decode(creator_id_en).decode('utf-8')
                                                creator_id = creator_id_str.split("-", 1)[1]
                                                author_name = subcommentsedges["author"]["name"]
                                                comments_image = subcommentsedges["author"]["imageUrl"]

                                            if "authorBadges" in subcommentsedges and subcommentsedges["authorBadges"]:
                                                author_tag_list = subcommentsedges["authorBadges"]
                                                author_tag = ",".join(author_tag_list)

                                            if "createdAt" in subcommentsedges and subcommentsedges["createdAt"]:
                                                pub_time_stamp = subcommentsedges["createdAt"]
                                                pub_time_dt = datetime.datetime.fromtimestamp(pub_time_stamp)
                                                pub_time = pub_time_dt.strftime('%Y-%m-%d %H:%M:%S')

                                            if "body" in subcommentsedges and subcommentsedges["body"]:
                                                body = subcommentsedges["body"]

                                            commentlist.append({
                                                "comments_type": "reply",
                                                "comments_id":subcomments_id,
                                                "creator_id": creator_id,
                                                "author_name":author_name,
                                                "author_tag":author_tag,
                                                "pub_time":pub_time,
                                                "pub_time_stamp":pub_time_stamp,
                                                "body":body,
                                                "is_add_on":is_add_on,
                                                "comments_image":comments_image,
                                                "parent_comments_id":comments_id,
                                                "replies_nums":0,
                                                "replies_cursor":"",
                                                "replies_finish":1
                                            })


            pageInfodict=project_data["comments"]["pageInfo"]
            if pageInfodict:
                if pageInfodict["hasNextPage"]:
                   comments_finish=0
                else:
                   comments_finish=1
                comments_cursor=pageInfodict["endCursor"]

            resultdata["comments"] = commentlist
            resultdata["comments_finish"] = comments_finish
            resultdata["comments_cursor"] = comments_cursor
            resultdata["success"] = 1
    except Exception as e:
        print("报错:", project_url,str(e))
        resultdata={"pid": pid, "success": 0}

    return resultdata
def get_Comments_replies(project_info):
    pid = project_info["pid"]
    project_url = project_info["project_url"]
    project_id = project_info["project_id"]
    comments_replies_cursor = project_info["replies_cursor"]
    comments_id = project_info["comments_id"]
    resultdata = {"pid": pid, "success": 0, "project_link": project_url, "project_id": project_id}

    try:
        commentsurl = project_url.split("?", 1)[0]
        commentsurl = commentsurl + "/comments"

        if str(comments_replies_cursor) == "":
            comments_replies_cursor = None

        impersonate_item = random.choice(impersonate_list)
        user_agent_item = random.choice(user_agent_list)
        headers = global_headers.copy()
        headers["x-csrf-token"] = global_param["csrf_token"]
        headers["referer"] = commentsurl
        headers["user-agent"] = user_agent_item
        cookies = global_cookies.copy()
        cookies["_ksr_session"] = global_param["session"]

        json_data = [
            {
                'operationName': None,
                'variables': {
                    'replyCursor': comments_replies_cursor,
                    'id': comments_id,
                },
                'query': 'query ($id: ID!, $replyCursor: String) {\n  node(id: $id) {\n    ...CommentInfo\n    ...CommentReplies\n    __typename\n  }\n}\n\nfragment CommentInfo on Comment {\n  id\n  body\n  createdAt\n  parentId\n  author {\n    id\n    imageUrl(width: 200)\n    name\n    url\n    __typename\n  }\n  removedPerGuidelines\n  authorBadges\n  canReport\n  canDelete\n  canPin\n  hasFlaggings\n  deletedAuthor\n  deleted\n  sustained\n  pinnedAt\n  authorCanceledPledge\n  authorBacking {\n    backingUrl\n    id\n    __typename\n  }\n  __typename\n}\n\nfragment CommentReplies on Comment {\n  replies(last: 25, before: $replyCursor) {\n    totalCount\n    nodes {\n      ...CommentInfo\n      __typename\n    }\n    pageInfo {\n      startCursor\n      hasPreviousPage\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n',
            },
        ]
        proxiesip = get_proxy(Use_proxy)
        response = cffirequests.post('https://www.kickstarter.com/graph', cookies=cookies, headers=headers, json=json_data, impersonate=impersonate_item,proxies=proxiesip)

        if response.status_code == 200:
            comments_finish=1
            comments_cursor=""
            responsetext = response.text
            jsondata = json.loads(responsetext)
            project_data = jsondata[0]["data"]
            if project_data is None:
                    return {"pid": pid, "success": 1, "project_link": project_url, "project_id": project_id,"comments_finish":1,"comments_cursor":"","comments_id":comments_id }

            commentlist=[]
            if project_data["node"]:
                if "replies" in project_data["node"] and project_data["node"]["replies"]:
                    subcommentsedgesnodes=project_data["node"]["replies"]["nodes"]
                    if subcommentsedgesnodes:
                        for subcommentsedges in subcommentsedgesnodes:
                            if subcommentsedges:
                                creator_id=""
                                author_name = ""
                                author_tag = ""
                                pub_time = ""
                                pub_time_stamp = 0
                                body = ""
                                comments_image = ""

                                subcomments_id = subcommentsedges["id"]
                                if "author" in subcommentsedges and subcommentsedges["author"]:
                                    creator_id_en = str(subcommentsedges["author"]["id"])
                                    creator_id_str = base64.b64decode(creator_id_en).decode('utf-8')
                                    creator_id = creator_id_str.split("-", 1)[1]
                                    author_name = subcommentsedges["author"]["name"]
                                    comments_image = subcommentsedges["author"]["imageUrl"]

                                if "authorBadges" in subcommentsedges and subcommentsedges["authorBadges"]:
                                    author_tag_list = subcommentsedges["authorBadges"]
                                    author_tag = ",".join(author_tag_list)

                                if "createdAt" in subcommentsedges and subcommentsedges["createdAt"]:
                                    pub_time_stamp = subcommentsedges["createdAt"]
                                    pub_time_dt = datetime.datetime.fromtimestamp(pub_time_stamp)
                                    pub_time = pub_time_dt.strftime('%Y-%m-%d %H:%M:%S')

                                if "body" in subcommentsedges and subcommentsedges["body"]:
                                    body = subcommentsedges["body"]

                                commentlist.append({
                                    "comments_type": "reply",
                                    "comments_id":subcomments_id,
                                    "creator_id":creator_id,
                                    "author_name":author_name,
                                    "author_tag":author_tag,
                                    "pub_time":pub_time,
                                    "pub_time_stamp":pub_time_stamp,
                                    "body":body,
                                    "is_add_on":0,
                                    "comments_image":comments_image,
                                    "parent_comments_id":comments_id,
                                    "replies_nums":0,
                                    "replies_cursor":"",
                                    "replies_finish":1
                                })

                    pageInfodict=project_data["node"]["replies"]["pageInfo"]
                    if pageInfodict:
                        if pageInfodict["hasPreviousPage"]:
                           comments_finish=0
                        else:
                           comments_finish=1
                        comments_cursor=pageInfodict["startCursor"]

            resultdata["comments"] = commentlist
            resultdata["replies_finish"] = comments_finish
            resultdata["replies_cursor"] = comments_cursor
            resultdata["comments_id"] = comments_id
            resultdata["success"] = 1
        else:
            raise Exception(response.status_code)
    except Exception as e:
        print("报错:", project_url,str(e))
        resultdata={"pid": pid, "success": 0}

    return resultdata
def downloadComments():
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


    while True:

        db = get_mysqldb()
        cursor = db.cursor()

        begin_postion=0
        end_postion=1000000

        querysql = """
              select pid,project_id,project_link as project_url,comments_cursor from main_info  
              where pid >=%s  AND pid<%s  and  comments_finish=0  ORDER BY reviews_num desc
               """%(begin_postion,end_postion)

        cursor.execute(querysql)  # 执行SQL语句
        scrapy_urls = cursor.fetchall()
        db.close()

        comments_is_done=False
        repliescomments_is_done=False
        if len(scrapy_urls) >0:
            try:
                    db = get_mysqldb()
                    with ThreadPoolExecutor(max_workers=Max_works) as t1:

                        obj_list1 = []
                        for scrapy_url in scrapy_urls:
                            obj_list1.append(t1.submit(get_Comments, scrapy_url))
                        for future in as_completed(obj_list1):
                             retrunrewards = future.result()

                             if retrunrewards["success"]==1:
                                 try:
                                     cursor = db.cursor()
                                     link_pid = retrunrewards["pid"]
                                     if "comments" in retrunrewards and  retrunrewards["comments"]:
                                         commentsinfos=retrunrewards["comments"]

                                         commentsinfosql = """ insert into comments_info(pid,project_id,project_link,comments_type,comments_id,creator_id,author_name,
                                                                                       comments_content,author_tag,pub_time,pub_time_stamp,
                                                                                       is_add_on,comments_image,parent_comments_id,replies_nums,replies_cursor,replies_finish) 
                                                                                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) 
                                          """
                                         commentsinfolist=[]
                                         for comments in commentsinfos:
                                             commentsinfolist.append((retrunrewards["pid"],retrunrewards["project_id"],retrunrewards["project_link"],comments["comments_type"],comments["comments_id"],comments["creator_id"],comments["author_name"],
                                                     comments["body"],comments["author_tag"], comments["pub_time"],comments["pub_time_stamp"],
                                                     comments["is_add_on"], comments["comments_image"],comments["parent_comments_id"],comments["replies_nums"],comments["replies_cursor"],comments["replies_finish"]
                                                     ))

                                         cursor.executemany(commentsinfosql,commentsinfolist)  # 执行SQL语句


                                     updatesql = """update main_info set comments_finish=%s,comments_cursor=%s  where pid=%s """ %(retrunrewards["comments_finish"],quotedStr(retrunrewards["comments_cursor"]),link_pid)
                                     cursor.execute(updatesql)
                                     db.commit()  # 提交
                                     print("Comments下载成功!")

                                 except Exception as e:
                                     print(str(e))
                                     db.rollback()  # 如果执行失败要回滚

            finally:
                 db.close()
        else:
            comments_is_done=True




        querysql2 = """
              select pid,project_id,project_link as project_url,comments_id,replies_cursor from comments_info
              where pid >=%s  AND pid<%s  and  is_add_on=1 and replies_finish=0   LIMIT 200
               """%(begin_postion,end_postion)

        db = get_mysqldb()
        cursor = db.cursor()
        cursor.execute(querysql2)  # 执行SQL语句
        repliesscrapy_urls = cursor.fetchall()
        db.close()


        if len(repliesscrapy_urls) >0:
            try:
                db = get_mysqldb()
                with ThreadPoolExecutor(max_workers=Max_works) as t2:

                    obj_list2 = []
                    for repliesscrapy_url in repliesscrapy_urls:
                        obj_list2.append(t2.submit(get_Comments_replies, repliesscrapy_url))
                    for future in as_completed(obj_list2):
                         retrunrewards2 = future.result()
                         if retrunrewards2["success"]==1:
                             try:
                                 cursor = db.cursor()
                                 if "comments" in retrunrewards2 and  retrunrewards2["comments"]:
                                     repliescommentsinfos=retrunrewards2["comments"]

                                     repliescommentsinfosql = """ insert into comments_info(pid,project_id,project_link,comments_type,comments_id,creator_id,author_name,
                                                                                   comments_content,author_tag,pub_time,pub_time_stamp,
                                                                                   is_add_on,comments_image,parent_comments_id,replies_nums,replies_cursor,replies_finish) 
                                                                               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) 
                                      """
                                     repliescommentsinfolist=[]
                                     for repliescomments in repliescommentsinfos:
                                         repliescommentsinfolist.append((retrunrewards2["pid"],retrunrewards2["project_id"],retrunrewards2["project_link"],repliescomments["comments_type"],repliescomments["comments_id"],repliescomments["creator_id"],repliescomments["author_name"],
                                                 repliescomments["body"],repliescomments["author_tag"], repliescomments["pub_time"],repliescomments["pub_time_stamp"],
                                                 repliescomments["is_add_on"], repliescomments["comments_image"],repliescomments["parent_comments_id"],repliescomments["replies_nums"],repliescomments["replies_cursor"],repliescomments["replies_finish"]
                                                 ))

                                     cursor.executemany(repliescommentsinfosql,repliescommentsinfolist)  # 执行SQL语句


                                 updatesql2 = """update comments_info set replies_finish=%s,replies_cursor=%s  where comments_id=%s """ %(retrunrewards2["replies_finish"],quotedStr(retrunrewards2["replies_cursor"]),quotedStr(retrunrewards2["comments_id"]))
                                 cursor.execute(updatesql2)
                                 db.commit()  # 提交
                                 print("repliesComments下载成功!")

                             except Exception as e:
                                 print(str(e))
                                 db.rollback()  # 如果执行失败要回滚
            finally:
                db.close()
        else:
            repliescomments_is_done=True



        if comments_is_done==True and repliescomments_is_done==True:
            print("COMMENTS数据已经爬取完成!")
            break

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

                print("访问网站成功",200)
                break;
            else:
                print("访问网站失败",response.status_code)
                time.sleep(1)
        except Exception as e:
            # print("连接代理服务器失败")
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


    downloadComments()


