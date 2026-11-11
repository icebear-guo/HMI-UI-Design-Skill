"""Seven explicit native-pixel canvases with bounded native fixture evidence."""
SIZES=((480,272),(800,480),(800,600),(1024,600),(1024,768),(1366,768),(1920,1080))
def dimensions(width,height):
    if type(width) is not int or type(height) is not int or (width,height) not in SIZES:
        raise ValueError('当前原生适配支持480×272、800×480、800×600、1024×600、1024×768、1366×768、1920×1080；不会自动改画布：'+str((width,height)))
    return width,height
def details(width,height):
    dimensions(width,height)
    size=(width,height)
    return {'width':width,'height':height,
            'native_status':'previous_native_samples_verified' if size==(1024,600) else 'native_fixture_runtime_display_verified',
            'copy_verified':True,
            'saved_geometry_before_project_resize_verified':size in ((1024,600),(1024,768),(800,480),(1920,1080)),
            'evidence_scope':'有限原厂样例的复制和显示；不代表全部控件、字体、业务行为或实体屏幕通过',
            'note':'该分辨率已有原厂样例显示验证；当前页面仍需核对。更改工程分辨率前请另存副本。'}
