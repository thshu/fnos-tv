import concurrent.futures
import json
import re
from functools import partial
from typing import List
from urllib.parse import urljoin
from venv import logger

import parsel
from curl_cffi import requests
from tqdm import tqdm

from Fuction import request_data
from core.danmu.base import GetDanmuBase
from core.danmu.danmuType import EpisodeDataDto


class GetDanmuTencent(GetDanmuBase):
    name = "腾讯视频"
    domain = "v.qq.com"

    def __init__(self):
        self.api_danmaku_base = "https://dm.video.qq.com/barrage/base/"
        self.api_danmaku_segment = "https://dm.video.qq.com/barrage/segment/"

    def get_link(self, url) -> List[str]:
        res = request_data("GET", url)
        res.encoding = res.apparent_encoding
        sel = parsel.Selector(res.text)
        title = sel.xpath('//title/text()').get().split('_')[0]
        vid = re.findall(f'"title":"{title}","vid":"(.*?)"', res.text)
        if vid:
            vid = vid[-1]
        if not vid:
            vid = re.search(r"/([a-zA-Z0-9]+)\.html", url)
            if vid:
                vid = vid.group(1)
        if not vid:
            logger.error("解析vid失败，请检查链接是否正确")
            return []
        res = request_data("GET", urljoin(self.api_danmaku_base, vid))
        if res.status_code != 200:
            logger.error("获取弹幕详情失败")
            return []
        # 使用线程池并行获取所有分段
        segment_indices = list(res.json().get("segment_index", {}).values())
        links = [urljoin(self.api_danmaku_segment,
                         vid + "/" + item.get("segment_name", "/")) for item in segment_indices]
        return links

    def parse(self, _data):
        data_list = []
        data = _data.json()
        for item in data.get("barrage_list", []):
            _d = self.get_data_dict()
            _d.time = int(item.get("time_offset", 0)) / 1000
            _d.text = item.get("content", "")
            _d.other['create_time'] = item.get('create_time', "")
            if item.get("content_style") != "":
                content_style = json.loads(item.get("content_style"))
                _d.color = int(content_style.get("color", "ffffff").replace("#", ""), 16)
            data_list.append(_d)
        return data_list

    def main(self, links):
        self.data_list = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(links))) as executor:
            fun = partial(self.request_data, requests, "GET")
            results = list(tqdm(executor.map(fun, links),
                                total=len(links),
                                desc="腾讯视频弹幕获取"))
            self.data_list.extend(results)

        return self.data_list

    def getImg(self, url):
        vid = re.search(r"/([a-zA-Z0-9]+)\.html", url)
        if vid:
            vid = vid.group(1)
        if not vid:
            return self.error("解析vid失败，请检查链接是否正确")
        cid = url.split('/')[-2]
        data = {
            "vid": vid,
            "cid": cid,
            "lid": "",
            "bIsGetUserCfg": True
        }
        res = request_data("POST",
                           "https://pbaccess.video.qq.com/trpc.danmu.danmu_switch_comm.DanmuSwitch/getVideoDanmuSwitch",
                           json=data)
        danmukey = res.json().get('data', {}).get('registResultInfo', {}).get('dataKey')
        res = request_data("POST", "https://pbaccess.video.qq.com/trpc.message.danmu_richdata.Richdata/GetRichData",
                           json={
                               "danmu_key": danmukey,
                               "vip_degree": 0
                           },
                           headers={
                               'origin': "https://v.qq.com",
                               'referer': "https://v.qq.com",
                           })
        emoji_infos = res.json().get('data', {}).get('emoji_configs', {}).get('emoji_infos', [])
        emoji_data_list = []
        for emoji_info in emoji_infos:
            emoji_data_list.append(
                {
                    'emoji_code': emoji_info.get('emoji_code'),
                    'emoji_url': emoji_info.get('emoji_url'),
                }
            )
        return emoji_data_list

    def get_episode_url(self, url: str) -> List[EpisodeDataDto]:
        res = request_data("GET", url)
        res.encoding = res.apparent_encoding
        sel = parsel.Selector(res.text)
        title = sel.xpath('//title/text()').get().split('_')[0]
        vid = re.findall(f'"title":"{title}","vid":"(.*?)"', res.text)
        if vid:
            vid = vid[-1]
        if not vid:
            vid = re.search(r"/([a-zA-Z0-9]+)\.html", url)
            if vid:
                vid = vid.group(1)
        if not vid:
            logger.error("解析vid失败，请检查链接是否正确")
            return []
        cid = re.findall('"cid":"(.*?)"', res.text)
        if cid:
            cid = cid[0]
        else:
            cid = re.search(fr"/([a-zA-Z0-9]+)/{vid}", url)
            if cid:
                cid = cid.group(1)
        if not cid:
            logger.error("解析cid失败，请检查链接是否正确")
            return []


        url = 'https://pbaccess.video.qq.com/trpc.universal_backend_service.page_server_rpc.PageServer/GetPageData'
        data = {
            "page_params": {
                "req_from": "web_vsite",
                "page_id": "vsite_episode_list",
                "page_type": "detail_operation",
                "id_type": "1",
                "page_size": "",
                "cid": cid,
                "vid": vid,
                "lid": "",
                "page_num": "",
                "page_context": "episode_begin=1&episode_end=100&episode_step=1&page_num=0&page_size=100",
                "detail_page_type": "1"
            },
            "has_cache": 1
        }
        res = request_data("POST", url, json=data, headers={
            'referer': 'https://v.qq.com/',
            'Cookie': 'video_platform=2; vversion_name=8.2.95'
        })
        json_data = res.json().get('data', {})
        data_list = json_data.get("module_list_datas", [{}])[0].get('module_datas', [{}])[0].get('item_data_lists',
                                                                                                 {}).get('item_datas',
                                                                                                         [])
        ret_data_list = []
        for item in data_list:
            item_params = item.get('item_params')
            _data = EpisodeDataDto(
                episodeTitle=item_params.get('video_subtitle'),
                episodeNumber=item_params.get('title'),
                url=f'https://v.qq.com/x/cover/{item_params.get("cid")}/{item_params.get("vid")}.html'
            )
            ret_data_list.append(_data)
        return ret_data_list
