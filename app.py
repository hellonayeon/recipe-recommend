from re import L
from flask import Flask, render_template, jsonify, request, redirect, url_for
from pymongo import MongoClient
from datetime import datetime, timedelta
import jwt # pip install PyJWT
import hashlib
import json
import secrets


# Flask 초기화
app = Flask(__name__)

# MongoDB 초기화
client = MongoClient('localhost', 27017)
db = client.dbrecipe

# JWT 암호화 키값 가져오기
with open('secrets.json') as file:
    secrets = json.loads(file.read())


@app.route('/')
def home():
    token_receive = request.cookies.get('mytoken')
    try:
        payload = jwt.decode(token_receive, secrets["SECRET_KEY"], algorithms=['HS256'])
        user_info = db.users.find_one({"email": payload["id"]})
        return render_template('index.html', user_info=user_info)
    except jwt.ExpiredSignatureError:
        return redirect(url_for("login", msg="로그인 시간이 만료되었습니다."))
    except jwt.exceptions.DecodeError:
        return redirect(url_for("login", msg="로그인 정보가 존재하지 않습니다."))


@app.route('/login')
def login():
    msg = request.args.get("msg")
    return render_template('login.html', msg=msg)


@app.route('/sign_in', methods=['POST'])
def sign_in():
    # 로그인
    email = request.form['email']
    password = request.form['password']

    pw_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
    result = db.users.find_one({'email': email, 'password': pw_hash})

    if result is not None:
        payload = {
         'id': email,
         'username' : result['username'],
         'exp': datetime.utcnow() + timedelta(seconds=60 * 60 * 24)  # 로그인 24시간 유지
        }
        token = jwt.encode(payload, secrets["SECRET_KEY"], algorithm='HS256')

        return jsonify({'result': 'success', 'token': token})
    # 찾지 못하면
    else:
        return jsonify({'result': 'fail', 'msg': '아이디/비밀번호가 일치하지 않습니다.'})


# 회원가입 정보 저장, 닉네임/이메일 중복 검사
@app.route('/sign_up/save', methods=['POST'])
def sign_up():
    username_receive = request.form['username_give']
    email_receive = request.form['email_give']
    username_exists = bool(db.users.find_one({"username": username_receive}))
    email_exists = bool(db.users.find_one({"email": email_receive}))

    if username_exists :
        return jsonify({'result': 'fail:username_exists'})
    if email_exists :
        return jsonify({'result': 'fail:email_exists'})

    password_receive = request.form['password_give']
    password_hash = hashlib.sha256(password_receive.encode('utf-8')).hexdigest()
    doc = {
        "username": username_receive,                               # 아이디
        "email" : email_receive,                                    # 이메일
        "password": password_hash,                                  # 비밀번호
        "profile_name": username_receive,                           # 프로필 이름 기본값은 아이디
        "profile_pic": "",                                          # 프로필 사진 파일 이름
        "profile_pic_real": "profile_pics/profile_placeholder.png", # 프로필 사진 기본 이미지
        "profile_info": ""                                          # 프로필 한 마디
    }
    db.users.insert_one(doc)
    return jsonify({'result': 'success'})


# 첫 화면 재료 항목 불러오기
@app.route('/ingredient', methods=['GET'])
def ingredient_listing():
    # 중복 제거
    irdnt = list(db.recipe_ingredient.distinct("IRDNT_NM"))
    return jsonify({'recipe_ingredient':irdnt})


# 레시피 검색할 리스트 & 좋아요 탭 불러오기
@app.route('/recipe/search', methods=['POST','GET'])
def make_recipe_list():
    mytoken = request.cookies.get('mytoken')
    try :
        payload = jwt.decode(mytoken, secrets["SECRET_KEY"], algorithms=['HS256'])
        username = (db.users.find_one({"email": payload["id"]}))['username']
        
        # 만약 POST 방식이면, 검색결과로 출력할 RECIPE_ID들을 DB에서 가져옴.
        if request.method == 'POST' : 
            data_we_want = []
            recipe_info = request.get_json()
            irdnt_nm = recipe_info['IRDNT_NM']
            nation_nm = recipe_info['NATION_NM']
            level_nm = recipe_info['LEVEL_NM']
            cooking_time = recipe_info['COOKING_TIME']

            level_nm_list = []
            for i in level_nm:
                level_nm_list.append({"LEVEL_NM": i})

            cooking_time_list = []
            for i in cooking_time:
                cooking_time_list.append({"COOKING_TIME": i})

            nation_nm_list = []
            if "서양, 이탈리아" in nation_nm:
                nation_nm_list.append({"NATION_NM": '서양'})
                nation_nm_list.append({"NATION_NM": '이탈리아'})
                nation_nm.remove('서양, 이탈리아')
            for i in nation_nm:
                nation_nm_list.append({"NATION_NM": i})
            selected_by_condition = list(db.recipe_basic.find({"$and": [{"$or": level_nm_list}, {"$or": nation_nm_list}, {"$or": cooking_time_list}]}))

            recipe_ids = set([selected['RECIPE_ID'] for selected in selected_by_condition])

            first_irdnt_ids = list(db.recipe_ingredient.find({"IRDNT_NM": irdnt_nm[0]}, {"_id": False, "RECIPE_ID": True}))
            ingredient_set = set([irdnt['RECIPE_ID'] for irdnt in first_irdnt_ids])
            for i in range(1, len(irdnt_nm)):
                irdnt_ids = list(db.recipe_ingredient.find({"IRDNT_NM": irdnt_nm[i]}, {"_id": False, "RECIPE_ID": True}))
                tmp_set = set([irdnt['RECIPE_ID'] for irdnt in irdnt_ids])
                ingredient_set = ingredient_set & tmp_set

            data_we_want = list(recipe_ids & ingredient_set)

        # 만약 'GET' 방식이면, 좋아요 탭을 위한 RECIPE_ID들을 DB에서 가져옴
        elif request.method == 'GET':
            data_we_want = list(db.likes.find({"username":username}).distinct("RECIPE_ID"))

        # DB에서 찾은 RECIPE_ID에 해당하는 레시피 정보들을 data_we_get에 저장 후 전송
        if data_we_want != []:
            projection = {"RECIPE_ID": True, "RECIPE_NM_KO": True, "SUMRY": True, "NATION_NM": True,
                        "COOKING_TIME": True, "QNT": True, "IMG_URL": True, "_id": False}
            data_we_get = []
            for i in range(len(data_we_want)):
                data_we_get.append(db.recipe_basic.find_one({"RECIPE_ID":int(data_we_want[i])}, projection))
                data_we_get[i]['likes_count'] = db.likes.count_documents({"RECIPE_ID":data_we_want[i]})
                data_we_get[i]['like_by_me'] = bool(db.likes.find_one({"RECIPE_ID":data_we_want[i], "username":username}))
            return jsonify({'msg': 'success', "data_we_get": data_we_get})
        else:
            return jsonify({'msg': 'nothing'})

    except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError):
        return redirect(url_for("/"))


# 레시피 상세정보 API
@app.route('/recipe/detail', methods=['GET'])
def get_recipe_detail():
    recipe_id = int(request.args.get("recipe-id"))
    mytoken = request.cookies.get('mytoken')
    try:    
        payload = jwt.decode(mytoken, secrets["SECRET_KEY"], algorithms=['HS256'])
        username = (db.users.find_one({"email": payload["id"]}))['username']
        # 레시피 정보
        projection = {"RECIPE_ID": True, "RECIPE_NM_KO": True, "SUMRY": True, "NATION_NM": True,
                    "COOKING_TIME": True, "QNT": True, "IMG_URL": True, "_id": False}
        info = db.recipe_basic.find_one({"RECIPE_ID": recipe_id}, projection)

        # 상세정보(조리과정)
        projection = {"COOKING_NO": True, "COOKING_DC": True, "_id": False}
        detail = list(db.recipe_number.find({"RECIPE_ID": recipe_id}, projection))

        # 재료정보
        projection = {"IRDNT_NM": True, "IRDNT_CPCTY": True, "_id": False}
        ingredients = list(db.recipe_ingredient.find({"RECIPE_ID": recipe_id}, projection))

        # 좋아요 정보
        like_info = [{}]
        like_info[0]['likes_count'] = db.likes.count_documents({"RECIPE_ID":recipe_id})
        like_info[0]['like_by_me'] = bool(db.likes.find_one({"RECIPE_ID":recipe_id, "username":username}))

        return jsonify({"info":info, "detail": detail, "ingredients":ingredients, "like_info":like_info})

    except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError):
        return redirect(url_for("/"))

# 댓글 목록 API
@app.route('/recipe/comment', methods=['GET'])
def get_comments():
    recipe_id = int(request.args.get("recipe-id"))
    comments = list(db.comment.find({"RECIPE_ID": recipe_id}, {"_id": False}))

    return jsonify(comments)


# 댓글 작성 API
@app.route('/recipe/comment', methods=['POST'])
def save_comment():
    recipe_id = int(request.form["recipe_id"])
    text = request.form["text"]

    nick_nm = request.form["nick_nm"]
    pw = request.form["pw"]

    # 이미 있는 닉네임인 경우 해당 레코드 반환
    used_nick_nm = db.comment.find_one({"NICK_NM": {"$in": [nick_nm]}})
    if used_nick_nm != None:
        return jsonify({'result': 'failure', 'msg': '이미 있는 닉네임입니다. 다른 닉네임을 입력해주세요!'})

    # [업로드 이미지 처리]
    # 클라이언트가 업로드한 파일을 서버에 저장
    fname = ""
    extension = ""
    today = today = datetime.now()  # 현재 시각 가져오기
    if len(request.files) != 0:
        file = request.files["img_src"]

        # 이미지 확장자
        # 가장 마지막 문자열 가져오기 [-1]
        # TODO: 아이폰 heic 확장자 이미지 예외처리 필요
        extension = file.filename.split('.')[-1]

        today = datetime.now()  # 현재 시각 가져오기
        time = today.strftime('%Y-%m-%d-%H-%M-%S')
        fname = f'file-{time}.{extension}'

        save_to = f'static/comment-images/{fname}'  # python f-string
        file.save(save_to)  # 날짜 기반 새로운 파일 이름 생성 후 프로젝트 static/comment-comment-images/ 폴더에 저장

    # 업데이트 날짜 표시
    date = today.strftime('%Y.%m.%d')

    # [DB 처리]
    doc = {
        'RECIPE_ID': recipe_id,
        'TEXT': text,
        'IMG_SRC': fname,
        'DATE': date,
        'NICK_NM': nick_nm,
        'PW': pw
    }

    db.comment.insert_one(doc)

    return jsonify({'result': 'success'})


# 댓글 삭제 API
@app.route('/recipe/comment', methods=['DELETE'])
def delete_comment():
    nick_nm = request.form["nick_nm"]
    pw = request.form["pw"]
    comment = db.comment.find_one({"NICK_NM": nick_nm}, {"_id": False})

    # 닉네임에 해당되는 비밀번호가 일치하지 않을 경우
    if(pw != comment["PW"]):
        return jsonify({'result': 'failure', 'msg': '비밀번호가 일치하지 않습니다!'})

    # 일치하는 경우 삭제
    db.comment.delete_one(comment)

    return jsonify({'result': 'success'})


# 좋아요 기능
@app.route('/recipe/update_like', methods=['POST'])
def update_like() :
    mytoken = request.cookies.get('mytoken')
    try :
        payload = jwt.decode(mytoken, secrets["SECRET_KEY"], algorithms=['HS256'])
        # 좋아요 수 변경
        user_info = db.users.find_one({"email": payload["id"]})
        recipe_id = int(request.form["recipe_id"])
        action = request.form["action"]
        doc = {
            "RECIPE_ID" : recipe_id,
            "username" : user_info["username"]
        }
        if action == "like" : 
            db.likes.insert_one(doc)
        else :
            db.likes.delete_one(doc)
        likes_count = db.likes.count_documents({"RECIPE_ID":recipe_id})
        return jsonify({"likes_count":likes_count})

    except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError):
        return redirect(url_for("/"))


if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)