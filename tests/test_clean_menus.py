import io,unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,ImageDraw
from astrbot_plugin_apis.entertainment_menu import render_menu
from astrbot_plugin_apis.sixty_cards import render_catalog


class CleanMenuTests(unittest.TestCase):
    def test_menus_keep_entries_and_parameters_without_repeated_footers(self):
        entries=[SimpleNamespace(name='今日老婆',type='image',valid=True),SimpleNamespace(name='笑话',type='text',valid=True)]
        rows=[{'name':'天气','category':'资讯','params':{'city':'城市'},'example':'/天气 上海'}]
        text=[];original=ImageDraw.ImageDraw.text
        def record(draw,xy,value,*args,**kwargs):
            text.append(str(value));return original(draw,xy,value,*args,**kwargs)
        with patch.object(ImageDraw.ImageDraw,'text',record):
            for data in (render_menu(entries),render_menu(entries,'image'),render_catalog(rows)):
                with Image.open(io.BytesIO(data)) as image:image.verify()
        self.assertIn('今日老婆',text);self.assertIn('/天气',text);self.assertIn('例：上海',text)
        self.assertFalse(any('部分接口' in line or '数据以源站为准' in line or '参数统一放命令后' in line for line in text))


if __name__=='__main__':unittest.main()
