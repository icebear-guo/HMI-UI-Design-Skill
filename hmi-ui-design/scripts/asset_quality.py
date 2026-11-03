"""Content checks for component PNGs, independent of file size and gallery references."""
from PIL import Image


def inspect_asset(path, expectation):
    if not isinstance(expectation, dict):
        raise ValueError('content_expectation required: derive it from source geometry, not exported PNG')
    mode = expectation.get('mode')
    if mode not in ('visible', 'empty_state'):
        raise ValueError('content_expectation.mode must be visible or explicitly empty_state')
    with Image.open(path) as image:
        alpha = image.convert('RGBA').getchannel('A')
        bbox = alpha.getbbox()
        visible = sum(alpha.histogram()[1:])
        total = image.width * image.height
        result = dict(alpha_bbox_px=None if bbox is None else list(bbox),
                      visible_pixels=visible, visible_fraction=visible / total)
        if mode == 'empty_state':
            if not expectation.get('reason') or visible:
                raise ValueError('empty_state needs a reason and must actually be empty')
            return result
        if not visible:
            raise ValueError('visible component PNG is completely transparent: ' + str(path))
        required = expectation.get('required_bbox_px')
        if (not isinstance(required, list) or len(required) != 4 or
                not all(type(v) is int for v in required) or
                not (0 <= required[0] < required[2] <= image.width and
                     0 <= required[1] < required[3] <= image.height)):
            raise ValueError('visible assets need source-derived required_bbox_px in LTRB pixels')
        tolerance = expectation.get('tolerance_px', 2)
        if type(tolerance) is not int or not 0 <= tolerance <= 4:
            raise ValueError('content bbox tolerance must be 0..4 pixels')
        if (bbox[0] > required[0] + tolerance or bbox[1] > required[1] + tolerance or
                bbox[2] < required[2] - tolerance or bbox[3] < required[3] - tolerance):
            raise ValueError(f'component content truncated: expected at least {required}, found {bbox}: {path}')
        minimum = expectation.get('min_visible_fraction', 0)
        if type(minimum) not in (int, float) or not 0 <= minimum <= 1:
            raise ValueError('min_visible_fraction must be 0..1')
        if result['visible_fraction'] < minimum:
            raise ValueError('component visible area below source expectation: ' + str(path))
        return result
