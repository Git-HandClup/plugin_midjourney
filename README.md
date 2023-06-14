# plugin_midjourney
***当前插件已更新，可同时支持有回调或者没有回调两种情况，如果没有回调地址就直接留空，将会默认查询任务进度来获取图片链接，并且将midjourney-proxy的固定url放进了配置文件中，只需要按照格式修改config.json文件中的midjourneyProxy后即可访问插件中的相关接口，注意！mj.py文件中有关于redis的配置，如果没有配置回调地址可以直接注释掉或者删除都行。***
1. 先安装redis依赖：**pip3 install redis**
2. 该项目是一个插件，插件应用于zhayujie / chatgpt-on-wechat，依赖于novicezk/midjourney-proxy
3. **在使用该插件前需要确保你是否已经搭建好[novicezk/midjourney-proxy](https://github.com/novicezk/midjourney-proxy)这个服务，因为如果没有这个服务，那么插件就相当于是摆设，每个命令其实都是调用这个服务里的接口，我只是做了一个适配。**
4. 插件的主要功能用于调用Midjourney，支持**imagine、upscale、variation、blend、describe**五个基本命令
5. 垫图的具体效果以及使用说明如图：

![1685949240478](https://github.com/Git-HandClup/plugin_midjourney/assets/38003767/dd067454-203b-40d1-8512-92fdcbc02526)![1685949271304](https://github.com/Git-HandClup/plugin_midjourney/assets/38003767/839e6a4a-59d9-4fc4-abad-cb3a92862922)

6. 该插件是参考了Summary插件，在接收到图片的时候会先将图片保存到本地（我没有做删除，你可以自己改），然后将图片内容转base64的方式保存在sqlite数据库中。
7. 该插件用到了redis进行轮询（能怎么简单怎么来），每隔30s拿着任务ID进行查询redis是否已经有结果，由于midjourney处于fast的速度下是一分钟出图，所以我这边设置的是超过90s以后会直接回复超时并停止。
8. 如何同时返回图片和对应的ID：我是直接修改了wechat_channel.py文件，在send方法中，当reply.type == ReplyType.IMAGE_URL时，原本的代码是什么我也忘记了，我是直接在midjourney返回图片链接的时候在后面加上了?id=xxxx，只需要将这个作为关键词进行分割字符串然后循环发送即可，这里需要提醒一下，因为midjourney的图片链接需要魔法才能访问的，所以在下载的时候需要设置代理，具体代码如下：
 ```python             
content = reply.content.split("?id=")
for index, item in enumerate(content):
	if index > 0:
		itchat.send("图片ID为：" + item, toUserName=receiver)
		logger.info("[WX] sendMsg={}, receiver={}".format(reply, receiver))
	else:
		proxy = conf().get("proxy", "")
		proxies = {"http": proxy, "https": proxy}
		pic_res = requests.get(item, proxies=proxies, stream=True)
		image_storage = io.BytesIO()
		for block in pic_res.iter_content(1024):
				image_storage.write(block)
		image_storage.seek(0)
		itchat.send_image(image_storage, toUserName=receiver)
		logger.info("[WX] sendImage url={}, receiver={}".format(item, receiver)) 
```
9. 最后说明：本人不擅长Python，只能依靠感觉来写，有写的不好的地方也请见谅，希望这个插件能够帮助大家更方便使用midjourney。
