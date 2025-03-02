import threading
import json

from config.DatabaseConfig import *
from utils.Database import Database
from utils.BotServer import BotServer
from utils.PreprocessW2V import PreprocessW2V as Preprocess
from models.intent.IntentModel_New import IntentModel
from models.ner.NerModel_New import NerModel
from utils.FindAnswer import FindAnswer
from customer import Customer

# 전처리 객체 생성
p = Preprocess(w2v_model='ko_with_corpus_mc1_menu_added.kv', userdic='utils/user_dic.txt')

# 개체명 인식 모델
ner = NerModel(proprocess=p)

cust=Customer()

# 의도 파악 모델
intent = IntentModel(proprocess=p, nermodel=ner, customer=cust)

wordtonum={
    "두":2, "세":3, "네":4,"다섯":5,"여섯":6,"일곱":7,"여덟":8,"아홉":9,"열":10
}


def to_client(conn, addr, params):
    db = params['db']

    try:
        db.connect()  # 디비 연결

        # 데이터 수신
        read = conn.recv(2048)  # 수신 데이터가 있을 때 까지 블로킹
        print('===========================')
        print('Connection from: %s' % str(addr))

        if read is None or not read:
            # 클라이언트 연결이 끊어지거나, 오류가 있는 경우
            print('클라이언트 연결 끊어짐')
            exit(0)


        # json 데이터로 변환
        recv_json_data = json.loads(read.decode())
        print("데이터 수신 : ", recv_json_data)
        query = recv_json_data['Query']

        # 의도 파악
        intent_name = intent.predict_class(query)
        tagword=intent.detailed_class_check(query)

        # 개체명 파악
        ner_predicts = ner.predict(query)


        # 답변 검색
        try:
            f = FindAnswer(db)
            answer, answer_code = f.search(intent_name, ner_predicts)
            if answer_code=="11":
                answer=''
                tempbag=[]
                for word, tag in ner_predicts:
                    if checker==1 and tag=="QT":
                        if word in wordtonum.keys():
                            num=wordtonum[word]
                        else:
                            num=1
                        cust.put_item(word, num)
                        answer+=word+' '+str(num)+', '
                    else:
                        cust.put_item(word, 1)
                        answer+=word+', '
                    checker=0

                    if word in intent.submenu:
                        tempbag=word
                        checker=1
                if checker==1:
                    cust.put_item(word, 1)
                    answer+=word+' '+str(num)+', '
   
                if len(tempbag)!=0:
                    answer=answer[:-2]+" 장바구니에 넣었습니다."
                else:
                    answer = "죄송합니다. 저희 매장에는 없는 메뉴입니다."
            if answer_code=="12":
                tempbag=[]
                for word, tag in ner_predicts:
                    if word in cust.bag:
                        cust.cancel_item(word)
                        tempbag.append(word)
                if len(tempbag)!=0:
                    answer=''
                    for word in tempbag:
                        answer+=word+', '
                    answer=answer[:-2]+" 장바구니에서 제외되었습니다."
                else:
                    answer = "해당 메뉴는 장바구니에 없습니다."
            if answer_code=='4':
                if intent_name=="메뉴안내":
                    search_done=0
                    for word, tag in ner_predicts:
                        if word in intent.submenu:
                            for cat in intent.menu.values():
                                for exactmenu in cat:
                                    if exactmenu['name']==word and search_done==0:
                                        answer=exactmenu['text']
                                        search_done=1
                                        break
                    
                    if search_done==0:
                        answer = "죄송해요 무슨 말인지 모르겠어요. 조금 더 공부 할게요."
                else:
                    answer=f.match_answer(tagword, intent_name, ner_predicts)
                if tagword=="가깝":
                    answer="여기서 가장 가까운 매장은 코엑스 도심공항점입니다."
            
            if answer_code=='3':
                answer, mod_menu=f.show_menu(tagword, intent.menu)

            if answer_code=='1':
                if tagword in ['취소', '못하', '미루', '미루워', '캔슬', '조정']:
                    if len(cust.reservation)==0:
                        answer=="취소할 수 있는 예약이 없습니다."
                    else: 
                        time, person= f.timeandperson(ner_predicts)
                        answer="해당 시간에 잡힌 예약이 없습니다."
                        for reserv in cust.reservation:
                            if reserv[0]==time:
                                cust.cancel_reserv(time)
                                answer==f"{time}시 예약을 취소하였습니다."
                else:
                    answer=''
                    time, person= f.timeandperson(ner_predicts)
                    if time!=None and person!=None:
                        answer+=time+'시 '+person+'명 예약합니다.'
                        cust.reserv(time, person)
                    else:
                        answer="예약창으로 이동합니다. 나머지 정보를 채워주십시오."

            #예약 내역 보여주기


                    





        except:
            answer = "죄송해요 무슨 말인지 모르겠어요. 조금 더 공부 할게요."
            answer_code = None

        send_json_data_str = {
            "Query" : query,
            "Answer": answer,
            "AnswerCode" : answer_code,
            "Intent": intent_name,
            "Intent_tag": tagword,
            "NER": str(ner_predicts) 
        }
        message = json.dumps(send_json_data_str)
        conn.send(message.encode())

    except Exception as ex:
        print(ex)

    finally:
        if db is not None: # db 연결 끊기
            db.close()
        conn.close()


if __name__ == '__main__':

    # 질문/답변 학습 디비 연결 객체 생성
    db = Database(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, db_name=DB_NAME
    )
    print("DB 접속")

    port = 5050
    listen = 100

    # 봇 서버 동작
    bot = BotServer(port, listen)
    bot.create_sock()
    print("bot start")

    while True:
        conn, addr = bot.ready_for_client()
        params = {
            "db": db
        }

        client = threading.Thread(target=to_client, args=(
            conn,
            addr,
            params
        ))
        client.start()
