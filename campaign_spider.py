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

def get_Campaign(project_info):
    pid = project_info["pid"]
    project_url = project_info["project_url"]
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


        json_data = [
            {
                'operationName': 'Campaign',
                'variables': {
                    'slug': slug,
                },
                'query': 'query Campaign($slug: String!) {\n  project(slug: $slug) {\n    id\n    isSharingProjectBudget\n    risks\n    story(assetWidth: 680)\n    storyRteVersion\n    currency\n    spreadsheet {\n      displayMode\n      public\n      url\n      data {\n        name\n        value\n        phase\n        rowNum\n        __typename\n      }\n      dataLastUpdatedAt\n      __typename\n    }\n    environmentalCommitments {\n      id\n      commitmentCategory\n      description\n      __typename\n    }\n    aiDisclosure {\n      fundingForAiAttribution\n      fundingForAiConsent\n      fundingForAiOption\n      generatedByAiConsent\n      generatedByAiDetails\n      otherAiDetails\n      involvesAi\n      involvesFunding\n      involvesGeneration\n      involvesOther\n      __typename\n    }\n    __typename\n  }\n}\n',
            },
        ]

        proxiesip = get_proxy(Use_proxy)
        response = cffirequests.post('https://www.kickstarter.com/graph', cookies=cookies,headers=headers, json=json_data, impersonate=impersonate_item,proxies=proxiesip)
        #
        # with open("Campaign.json", "w", encoding="utf-8") as fout:
        #     fout.write(response.text)

        # with open("Campaign.json", "r", encoding="utf-8") as fin:
        #     responsetext = fin.read()


        if response.status_code==200:

            responsetext=response.text
            jsondata=json.loads(responsetext)
            project_data=jsondata[0]["data"]["project"]
            if project_data is None:
                return {"pid": pid, "success": 1,"project_link":project_url,"project_id":project_id }

            if project_data:

                sub_titles_text=""
                total_background_text=""
                story=""
                background_story=""
                risk_and_challenge=""
                sub_titles=""
                existing_budget="0"
                existing_environmental_commitments="0"
                existing_use_of_AI="0"

                imageLists = []
                videoLists = []
                voiceLists = []
                image_num=0
                voice_num=0
                video_num=0
                display_budget = 0
                budget_list=[]
                timeline="0"


                if "risks" in project_data and  project_data["risks"]:
                   risk_and_challenge=project_data["risks"]


                if "story" in project_data and project_data["story"]:
                    story = project_data["story"]
                    story=story.replace("</h3>","</h3>\n")
                    story=story.replace("</p>", "</p>\n")
                    soup = BeautifulSoup(story, 'html.parser')
                    background_story=soup.get_text()
                    background_story = re.sub(r'\n{2}', "\n", background_story)

                    story_html = etree.HTML(story)

                    timeline_node=story_html.xpath('//h3[contains(@id,"Timeline")]')
                    if timeline_node:
                       timeline="1"

                    titlesnodes = soup.find_all("h3")
                    for titlesnode in titlesnodes:
                        stext = titlesnode.getText()
                        stext = stext.strip()
                        if stext != "":
                            sub_titles = sub_titles + "\n" + stext


                    figurenodes = soup.find_all("figure")

                    figcaptionnum=0
                    voicenoderownum=0
                    for figurenode in figurenodes:
                        imgnode = figurenode.find("img")
                        if imgnode:
                            figcaptionnum+=1
                            img_url=imgnode["src"]
                            captionnode=figurenode.find("figcaption")
                            if captionnode:
                                img_caption=captionnode.getText()
                            else:
                                img_caption=""
                            imageLists.append({"row_num":figcaptionnum,"part_of":"body","img_url":img_url,"img_caption":img_caption})
                        voicenode = figurenode.find("source",attrs={"type": "audio/mp3"})
                        if voicenode:
                            voicenoderownum+=1
                            voice_url=voicenode["src"]
                            voiceLists.append({"row_num":voicenoderownum,"voice_url":voice_url})

                    voice_num=len(voiceLists)

                    image_num=len(imageLists)

                    videorownum=0
                    iframenodes = soup.find_all("iframe")
                    for iframenode in iframenodes:
                         video_url= iframenode["src"]
                         videorownum+=1
                         videoLists.append({"row_num":videorownum,"part_of":"body","video_url":video_url} )

                    vidionodes = soup.find_all("video")
                    for vidionode in vidionodes:
                        videosource = vidionode.find("source")
                        video_url = videosource["src"]
                        videorownum += 1
                        videoLists.append({"row_num": videorownum, "part_of": "body", "video_url": video_url})

                    video_num=len(videoLists)

                if "spreadsheet" in project_data and  project_data["spreadsheet"]:
                   if project_data["spreadsheet"]["public"]==True:
                      existing_budget="1"


                use_of_AI_str=""
                useofailist=[]
                ai_description=""
                ai_rownum=0

                if "aiDisclosure" in project_data and project_data["aiDisclosure"]:
                    if project_data["aiDisclosure"]["involvesAi"] == True:
                        existing_use_of_AI = "1"

                    if project_data["aiDisclosure"]["involvesFunding"] == True:
                        use_of_AI_str+="My project seeks funding for AI technology.\n\n"
                        ai_description+="My project seeks funding for AI technology.\n\n"

                    if project_data["aiDisclosure"]["fundingForAiConsent"] == True:
                        use_of_AI_str  +="For the database or source that I will use or will create, the consent of the persons whose works or information incorporated have been obtained.\n\n"
                        ai_description +="For the database or source that I will use or will create, the consent of the persons whose works or information incorporated have been obtained.\n\n"

                    if project_data["aiDisclosure"]["involvesOther"] == True:
                        use_of_AI_str+=project_data["aiDisclosure"]["otherAiDetails"] +"\n\n"
                        ai_description+=project_data["aiDisclosure"]["otherAiDetails"] +"\n\n"

                    if project_data["aiDisclosure"]["involvesGeneration"] == True:
                        use_of_AI_str+="I plan to use AI-generated content in my project.\n\n"
                        ai_description += "I plan to use AI-generated content in my project.\n\n"

                    if project_data["aiDisclosure"]["fundingForAiOption"]:
                        use_of_AI_str += "There is or will be an o…t-out for those owners.\n"
                        ai_description += "There is or will be an o…t-out for those owners.\n\n"

                    if project_data["aiDisclosure"]["fundingForAiConsent"]:

                        use_of_AI_str += "For the database or source that I will use or will create, the consent of the persons whose works or information are incorporated has been or will be obtained.\n"
                        ai_description +="For the database or source that I will use or will create, the consent of the persons whose works or information are incorporated has been or will be obtained.\n\n"


                    if project_data["aiDisclosure"]["fundingForAiAttribution"]:

                        use_of_AI_str += "The owners of these works are or will be receiving credit for their work.\n"
                        ai_description +="The owners of these works are or will be receiving credit for their work.\n\n"

                    if project_data["aiDisclosure"]["generatedByAiDetails"]:
                        ai_rownum+=1
                        use_of_AI_str += "What parts of your project will use AI generated content? Please be as specific as possible.\n"
                        use_of_AI_str += "  "+project_data["aiDisclosure"]["generatedByAiDetails"] +"\n\n"
                        useofailist.append({"row_num":ai_rownum,
                                            "ai_question":"What parts of your project will use AI generated content? Please be as specific as possible.",
                                            "ai_answer":project_data["aiDisclosure"]["generatedByAiDetails"]})


                    if project_data["aiDisclosure"]["generatedByAiConsent"]:
                        ai_rownum += 1
                        use_of_AI_str += "Do you have the consent of owners of the works that were (or will be) used to produce the AI generated portion of your projects? Please explain.\n"
                        use_of_AI_str += "  "+project_data["aiDisclosure"]["generatedByAiConsent"] +"\n\n"
                        useofailist.append({"row_num":ai_rownum,
                                            "ai_question":"Do you have the consent of owners of the works that were (or will be) used to produce the AI generated portion of your projects? Please explain.",
                                            "ai_answer":project_data["aiDisclosure"]["generatedByAiConsent"]})


                environmental_commitments_text=""
                environmental_commitments={}

                if "environmentalCommitments" in project_data and  project_data["environmentalCommitments"]:
                   design = ""
                   recyclability = ""
                   materials = ""
                   factories = ""
                   distribution = ""
                   something_else=""
                   existing_environmental_commitments="1"
                   environmental_commitments_text+="Visit our Environmental Resources Center to learn how Kickstarter encourages sustainable practices.\n\n"

                   for commitments_item in project_data["environmentalCommitments"]:

                       if commitments_item["commitmentCategory"]=="long_lasting_design":
                           environmental_commitments_text += "Long-lasting Design\n"
                           environmental_commitments_text += commitments_item["description"]+"\n\n"
                           design=commitments_item["description"]


                       if commitments_item["commitmentCategory"]=="reusability_and_recyclability":
                           environmental_commitments_text += "Reusability and recyclability\n"
                           environmental_commitments_text += commitments_item["description"]+"\n\n"
                           recyclability = commitments_item["description"]


                       if commitments_item["commitmentCategory"]=="sustainable_materials":
                           environmental_commitments_text += "Sustainable materials\n"
                           environmental_commitments_text += commitments_item["description"]+"\n\n"
                           materials=commitments_item["description"]


                       if commitments_item["commitmentCategory"]=="environmentally_friendly_factories":
                           environmental_commitments_text += "Environmentally friendly factories\n"
                           environmental_commitments_text += commitments_item["description"]+"\n\n"
                           factories = commitments_item["description"]


                       if commitments_item["commitmentCategory"]=="sustainable_distribution":
                           environmental_commitments_text += "Sustainable distribution\n"
                           environmental_commitments_text += commitments_item["description"]+"\n\n"
                           distribution = commitments_item["description"]

                       if commitments_item["commitmentCategory"]=="something_else":
                           environmental_commitments_text += "Something else\n"
                           environmental_commitments_text += commitments_item["description"]+"\n\n"
                           something_else = commitments_item["description"]

                   environmental_commitments={"design":design,
                                              "recyclability":recyclability,
                                              "materials":materials,
                                              "factories":factories,
                                              "distribution":distribution,
                                              "something_else":something_else
                                             }


                if background_story!="":
                    total_background_text+="\n\n"+"Story\n\n"+background_story
                    sub_titles_text+="Story\n"
                    if sub_titles!="":
                        sub_titles_text +=sub_titles.strip()+"\n"

                if existing_budget=="1":
                        sub_titles_text +="Project budget\n"

                if risk_and_challenge!="":
                    total_background_text+="\n\n"+"Risks and challenges"+"\n\n"+risk_and_challenge
                    sub_titles_text += "Risks\n"
                if use_of_AI_str!="":
                    total_background_text+="\n\n"+"Use of AI"+"\n\n"+use_of_AI_str
                    sub_titles_text += "Use of AI\n"
                if environmental_commitments_text!="":
                    total_background_text+="\n\n"+"Environmental commitments"+"\n\n"+environmental_commitments_text
                    sub_titles_text += "Environmental commitments\n"




                main_text={
                    "story":total_background_text,
                    # "subtitles":sub_titles_text,
                    # "background_story":story,
                    "risk_and_challenge":risk_and_challenge,
                    # "existing_budget":existing_budget,
                    # "display_budget":display_budget,
                    "existing_environmental_commitments":existing_environmental_commitments,
                    "existing_use_of_AI":existing_use_of_AI,
                    "image_num":image_num,
                    "video_num":video_num,
                    # "voice_num":voice_num,
                    "use_of_ai":use_of_AI_str,
                    "environmental_commitments":environmental_commitments_text,
                    "timeline":timeline,
                    "budget": existing_budget
                }

                resultdata["main_text"]=main_text
                # resultdata["budget"]=budget_list
                resultdata["image_info"]=imageLists
                resultdata["video_info"]=videoLists
                # resultdata["voice_info"]=voiceLists
                # resultdata["ai_question_answer"]=useofailist
                # resultdata["environmental_commitments"] = environmental_commitments
                resultdata["success"]=1
    except Exception as e:
        print("报错:", project_url,str(e))
        resultdata={"pid": pid, "success": 0}

    return resultdata

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
def downloadCampaigninfo():

    retry_number=0
    while True:

        db = get_mysqldb()
        cursor = db.cursor()



        begin_postion=0
        end_postion=1000000
        querysql = """
              select pid,project_id, project_url  from crawling_url where pid >=%s AND pid<%s AND campaign =0  LIMIT 2000
               """%(begin_postion,end_postion)


        cursor.execute(querysql)  # 执行SQL语句
        scrapy_urls = cursor.fetchall()
        db.close()


        if len(scrapy_urls) ==0:
              break
            # db = get_mysqldb()
            # cursor = db.cursor()
            # updatesql = """ update schedule_table set begin_postion=%s  where  category="CAMPAIGN"  """ %end_postion
            # cursor.execute(updatesql)
            # db.commit()  # 提交
            # db.close()
        else:
            try:
                db = get_mysqldb()
                with ThreadPoolExecutor(max_workers=Max_works) as t1:

                    obj_list1 = []
                    for scrapy_url in scrapy_urls:
                        obj_list1.append(t1.submit(get_Campaign,scrapy_url))

                    for future in as_completed(obj_list1):
                         retrunrewards = future.result()


                         if retrunrewards["success"]==1:
                             try:
                                 cursor = db.cursor()
                                 link_pid = retrunrewards["pid"]
                                 if "main_text" in retrunrewards and retrunrewards["main_text"]:
                                     main_text=retrunrewards["main_text"]

                                     insertmain_textsql = """ insert into campaign_info(pid,project_id,project_link,story,risk_and_challenge,
                                                                                   use_of_ai,environmental_commitments,timeline,budget,image_num,video_num)
                                                                               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                      """
                                     insertmain_textdata=[(retrunrewards["pid"],retrunrewards["project_id"],retrunrewards["project_link"],main_text["story"],main_text["risk_and_challenge"],
                                             main_text["use_of_ai"], main_text["environmental_commitments"],main_text["timeline"],main_text["budget"],main_text["image_num"],  main_text["video_num"]
                                             )]

                                     cursor.executemany(insertmain_textsql,insertmain_textdata)  # 执行SQL语句

                                 if "image_info" in retrunrewards and retrunrewards["image_info"]:
                                     image_info=retrunrewards["image_info"]


                                     insertimage_infosql = """ insert into image_info(pid,project_id,project_link,row_num,image_url,image_title)
                                                             VALUES(%s,%s,%s,%s,%s,%s) """
                                     insertimage_infos = []
                                     for datas in image_info:
                                         insertimage_infos.append((retrunrewards["pid"],retrunrewards["project_id"],retrunrewards["project_link"],datas["row_num"],datas["img_url"],datas["img_caption"]))

                                     cursor.executemany(insertimage_infosql,insertimage_infos)
                                 if "video_info" in retrunrewards and retrunrewards["video_info"]:
                                     image_info2=retrunrewards["video_info"]


                                     insertimage_infosql2 = """ insert into video_info(pid,project_id,project_link,row_num,video_url) 
                                                             VALUES(%s,%s,%s,%s,%s) """
                                     insertimage_infos2 = []
                                     for datas in image_info2:
                                         insertimage_infos2.append((retrunrewards["pid"],retrunrewards["project_id"],retrunrewards["project_link"],datas["row_num"],datas["video_url"]))

                                     cursor.executemany(insertimage_infosql2,insertimage_infos2)



                                 updatesql = """update crawling_url set campaign=1 where pid=%s """ %link_pid
                                 cursor.execute(updatesql)
                                 db.commit()  # 提交
                                 print("campaign下载成功!")

                             except Exception as e:
                                 print(str(e))
                                 db.rollback()  # 如果执行失败要回滚

            finally:
                db.close()
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

    # aaa=get_Campaign({"pid":99,"project_id":"1998400303", "project_url":"https://www.kickstarter.com/projects/bladebooster/blade-booster?ref=discovery_category&term=budget&total_hits=70273&category_id=337"})
    # abc=json.dumps(aaa)
    # with open("page.json", "w", encoding="utf-8") as fout:
    #     fout.write(abc)
    downloadCampaigninfo()