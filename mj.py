# encoding:utf-8
import base64
import json
import os
import re
import sqlite3
import time
import requests

import plugins
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from common.log import logger
from bridge.context import ContextType
from config import conf
from plugins import *


@plugins.register(
    name="mj",
    desire_priority=-1,
    desc="midjourneyApi调用",
    version="2.0",
    author="amiliko",
)
class Mj(Plugin):
    def __init__(self):
        super().__init__()
        try:
            curdir = os.path.dirname(__file__)
            config_path = os.path.join(curdir, "config.json")
            if not os.path.exists(config_path):
                raise Exception("config.json not found")
            else:
                with open(config_path, "r") as f:
                    conf = json.load(f)
            db_path = os.path.join(curdir, "chat_images.db")
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            c = self.conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS chat_images
                        (sessionid TEXT, msgid INTEGER, content TEXT, type TEXT, timestamp INTEGER,
                        PRIMARY KEY (sessionid, msgid))''')
            self.conn.commit()
            self.midjourneyProxy = conf["midjourneyProxy"]
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            self.handlers[Event.ON_RECEIVE_MESSAGE] = self.on_receive_message
            logger.info("[Midjourney] inited")
        except Exception as e:
            logger.warn("[Midjourney] init failed")
            raise e

    def get_help_text(self, verbose=False, **kwargs):
        help_text = "输入mj关键词会根据文字描述自动触发Midjourney的画图"
        if not verbose:
            return help_text
        help_text += "\n使用说明：\n\n"
        help_text += f"imagine 命令: 根据给出的描述可以按照描述来绘画，相关参数请自行搜索。\n\n"
        help_text += f"upscale 命令: 根据给出的ID + U1可以根据ID来查找对应的绘图（通常是草稿），最后根据U1指向草稿中的第一张进行放大处理。\n\n"
        help_text += f"variation 命令: 根据给出的(ID + V1)可以根据ID来查找对应的绘图（通常是草稿），最后根据U1指向草稿中的第一张进行微调处理。\n\n"
        help_text += f"blend 命令: blend + 数字，根据数字在聊天记录中按照倒序来查找指定张数图片，并将找到的图片进行结合处理，最少两张，最多四张。\n\n"
        help_text += f"describe 命令: describe + 数字，根据数字在聊天记录中按照倒序来查找图片，最后一次发送的指定为第一张，以此类推。"
        return help_text

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type != ContextType.TEXT:
            return

        content = e_context["context"].content
        content_list = e_context["context"].content.split(maxsplit=2)

        if content.startswith(f"mj"):
            query = content_list[1].strip()
            if query == "imagine":
                imagine = self._get_imagine(content_list[2].strip())
                image = self._get_midjourney_task(imagine["result"], "image")
            elif query == "upscale" or query == "variation":
                imagine = self._get_upscale_or_variation(content_list[2].strip())
                image = self._get_midjourney_task(imagine["result"], "image")
            elif query == "blend":
                if 1 < int(content_list[2]) < 4:
                    images = self._get_chat_history_images(e_context, content_list[2], True)
                    if len(images) == int(content_list[2]):
                        imagine = self._get_blend(images)
                        image = self._get_midjourney_task(imagine["result"], "image")
                    else:
                        reply = Reply(ReplyType.TEXT, f"聊天记录中的图片数量少于指定数量，无法进行垫图操作")
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                        return
                else:
                    reply = Reply(ReplyType.TEXT, f"图片数量不符合要求无法进行垫图操作")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                    return
            elif query == "describe":
                image = self._get_chat_history_images(e_context, content_list[2], False)
                if len(image) > 0:
                    imagine = self._get_describe(image)
                    prompt = self._get_midjourney_task(imagine["result"], "describe")
                    text = self._format_text(prompt)
                    reply = Reply(ReplyType.TEXT, f"{text}")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                else:
                    reply = Reply(ReplyType.TEXT, f"未找到对应图片，请重新指定图片")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                return
            else:
                reply = Reply(ReplyType.TEXT, f"调用mj发生错误，请检查指令或者描述是否有误。")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                return
            if image is not None:
                image += "?id=" + imagine["result"]
            else:
                reply = Reply(ReplyType.TEXT, f"调用mj超时，请检查指令或者描述是否有误。")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                return
            reply = Reply(ReplyType.IMAGE_URL, image)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑

    def on_receive_message(self, e_context: EventContext):
        context = e_context['context']

        if context.type == ContextType.IMAGE:
            content = context.content[:]
            msg = e_context['context']['msg']
            msg.prepare()
            open(content, "rb")
            img_base64 = self._convert_base64(context.content)
            cmsg: ChatMessage = e_context['context']['msg']
            session_id = cmsg.from_user_id
            if conf().get('channel_type', 'wx') == 'wx' and cmsg.from_user_nickname is not None:
                session_id = cmsg.from_user_nickname  # itchat channel id会变动，只好用群名作为session id

            self._insert_record(session_id, cmsg.msg_id, "data:image/png;base64," + img_base64, str(context.type),
                                cmsg.create_time)

    def _get_imagine(self, query):
        url = self.midjourneyProxy + "/submit/imagine"
        try:
            headers = {"Content-Type": "application/json"}
            data = json.dumps({"action": "IMAGINE", "prompt": query})
            response = requests.post(url, headers=headers, data=data)
            return json.loads(response.text)
        except Exception:
            return None

    def _get_upscale_or_variation(self, query):
        url = self.midjourneyProxy + "/submit/simple-change"
        try:
            headers = {"Content-Type": "application/json"}
            data = json.dumps({"content": query})
            response = requests.post(url, headers=headers, data=data)
            return json.loads(response.text)
        except Exception:
            return None

    def _get_blend(self, data):
        url = self.midjourneyProxy + "/submit/blend"
        try:
            images = []
            headers = {"Content-Type": "application/json"}
            for i in range(len(data)):
                record = list(data[i])
                images.append(record[2])
            data = json.dumps({"base64Array": images})
            response = requests.post(url, headers=headers, data=data)
            return json.loads(response.text)
        except Exception:
            return None

    def _get_describe(self, data):
        url = self.midjourneyProxy + "/submit/describe"
        try:
            image = ""
            headers = {"Content-Type": "application/json"}
            for i in range(len(data)):
                record = list(data[i])
                image = record[2]
            data = json.dumps({"base64": image})
            response = requests.post(url, headers=headers, data=data)
            return json.loads(response.text)
        except Exception:
            return None

    def _get_chat_history_images(self, e_context: EventContext, limit, multiple=True):
        msg: ChatMessage = e_context['context']['msg']
        session_id = msg.from_user_id
        if conf().get('channel_type', 'wx') == 'wx' and msg.from_user_nickname is not None:
            session_id = msg.from_user_nickname  # itchat channel id会变动，只好用名字作为session id
        offset = -1
        if not multiple:
            offset = int(limit) - 1
        records = self._get_records(session_id, limit, offset)
        return records

    def _convert_base64(self, image):
        curdir = os.getcwd()
        image_path = os.path.join(curdir, image)
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read())
        return encoded_string.decode('utf-8')

    def _insert_record(self, session_id, msg_id, content, msg_type, timestamp):
        c = self.conn.cursor()
        logger.debug(
            "[Midjourney] insert record: {} {} {} {} {}".format(session_id, msg_id, content, msg_type, timestamp))
        c.execute("INSERT OR REPLACE INTO chat_images VALUES (?,?,?,?,?)",
                  (session_id, msg_id, content, msg_type, timestamp))
        self.conn.commit()

    def _format_text(self, prompt):
        prompt_list = prompt.split("\n")
        text = ''
        index = 1
        for prompt in range(len(prompt_list)):
            if len(prompt_list[prompt]) > 0:
                text_arr = prompt_list[prompt].split(maxsplit=1)
                format_text = text_arr[1]
                format_text = format_text.replace("[", "").replace("]", "")
                format_text = format_text.replace("'", "").replace("'", "")
                format_text = re.sub('\(.*?\)', '', format_text)
                line = ""
                if index < 4:
                    line = "\n\n"
                text = text + str(index) + '. ' + format_text + line
                index += 1
        return text

    def _get_records(self, session_id, limit, offset):
        c = self.conn.cursor()
        if offset >= 0:
            c.execute("SELECT * FROM chat_images WHERE sessionid=? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                      (session_id, 1, offset))
        else:
            c.execute("SELECT * FROM chat_images WHERE sessionid=? ORDER BY timestamp DESC LIMIT ?",
                      (session_id, limit))
        return c.fetchall()

    def _get_midjourney_task(self, id, type):
        url = self.midjourneyProxy + "/task/" + id + "/fetch"
        while True:
            headers = {"Content-Type": "application/json"}
            response = requests.get(url, headers=headers)
            result = json.loads(response.text)
            # 当前任务已提交或者正在进行中时就默认睡眠30s
            if result["status"] == "SUBMITTED" or result["status"] == "IN_PROGRESS":
                time.sleep(30)
            elif result["status"] == "SUCCESS":
                if type == "image":
                    return result["imageUrl"]
                else:
                    return result["prompt"]
            elif result["status"] == "FAILURE":
                return None
