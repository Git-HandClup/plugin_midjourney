# plugin_midjourney
1. 插件应用于zhayujie / chatgpt-on-wechat，依赖于novicezk/midjourney-proxy
2. **在使用该插件前需要确保你是否已经搭建好[novicezk/midjourney-proxy](https://github.com/novicezk/midjourney-proxy)这个服务，因为如果没有这个服务，那么插件就相当于是摆设，每个命令其实都是调用这个服务里的接口，我只是做了一个适配。**
3. 当前插件为最终版本，不需要提供回调地址即可直接使用，只需要改动config.json中的midjourneyProxy地址即可，这个地址指向的是midjourney-proxy这个服务。
 
4. 插件的主要功能用于调用Midjourney，支持**imagine、upscale、variation、blend、describe**五个基本命令

6. 垫图的具体效果以及使用说明如图：

![1685949240478](https://github.com/Git-HandClup/plugin_midjourney/assets/38003767/dd067454-203b-40d1-8512-92fdcbc02526)![1685949271304](https://github.com/Git-HandClup/plugin_midjourney/assets/38003767/839e6a4a-59d9-4fc4-abad-cb3a92862922)

6. 如何同时返回图片和对应的ID：我是直接修改了wechat_channel.py文件，在send方法中，当reply.type == ReplyType.IMAGE_URL时，原本的代码是什么我也忘记了，我是直接在midjourney返回图片链接的时候在后面加上了?id=xxxx，只需要将这个作为关键词进行分割字符串然后循环发送即可，这里需要提醒一下，因为midjourney的图片链接需要魔法才能访问的，所以在下载的时候需要设置代理，具体代码如下：
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
