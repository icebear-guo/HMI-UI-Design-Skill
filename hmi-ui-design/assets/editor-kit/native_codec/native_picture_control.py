"""Native 0x5009 static picture cloning/editing from verified vendor templates."""
from dataclasses import dataclass
from pathlib import Path
import sys,copy,struct
import native_support
from mcs_window_archive import Reader,ControlRecord,FormatError
from mcs_button_control import CString
from 原生界面样式 import CommonEnvelope,GenericMetadata

# Both are actual native-saved zero-event records. Preserve the trailing flags;
# their values are not treated as event definitions or guessed display options.
KNOWN_STATIC_METADATA={bytes(12),bytes.fromhex('000000000000010000000000')}

def validate_static_donor(picture):
    if picture.common.animations:raise FormatError('不能克隆带动画图片')
    raw=picture.common.metadata.value
    metadata=GenericMetadata.parse(raw)
    if metadata.events or metadata.to_bytes()!=raw or raw not in KNOWN_STATIC_METADATA:
        raise FormatError('图片供体存在事件或未标定附加字段；保留原厂数据并先标定，不清零绕过')

@dataclass
class PictureControl:
    common:CommonEnvelope
    image:CString

    @classmethod
    def parse(cls,record):
        if record.type_id!=0x5009:raise FormatError('不是原生图片控件 0x5009')
        common=CommonEnvelope.parse(record);r=Reader(common.content)
        if r.u32()!=0x80:raise FormatError('目前只支持已验证的图库引用图片，未验证内嵌图分支')
        image=CString.parse(r)
        if not image.value or r.pos!=len(common.content):raise FormatError('图库名为空或存在未验证的图片尾部')
        result=cls(common,image)
        if result.to_record().payload!=record.payload:raise FormatError('图片控件不能精确回环')
        return result

    def to_record(self):
        self.common.content=struct.pack('<I',0x80)+self.image.to_bytes()
        return self.common.to_record()

    def edit(self,*,name=None,bounds=None,image=None):
        if self.common.animations:
            raise FormatError('带点击事件/动画的图片仅支持读取；编辑和克隆尚未标定')
        result=copy.deepcopy(self)
        if name is not None:
            if not isinstance(name,str) or not name or '\0' in name or len(name)>32:raise ValueError('控件名必须为 1～32 字符')
            result.common.name.value=name
        if bounds is not None:
            if len(bounds)!=4 or not all(type(v)is int for v in bounds) or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:raise ValueError('控件矩形不合法')
            result.common.set_rect(bounds)
        if image is not None:
            if not isinstance(image,str) or not image or '\0' in image:raise ValueError('图库图片名不合法')
            result.image.value=image
        record=result.to_record();assert PictureControl.parse(record).to_record().payload==record.payload
        return record
