import math
from string import Template
import typing

import vapoursynth as vs
from vapoursynth import core


__all__ = ["DFTTest", "DFTTest2"]


# https://github.com/HomeOfVapourSynthEvolution/VapourSynth-DFTTest/blob/
# bc5e0186a7f309556f20a8e9502f2238e39179b8/DFTTest/DFTTest.cpp#L518
def normalize(
    window: typing.Sequence[float],
    block_size: int,
    block_step: int
) -> typing.List[float]:

    nw = [0.0] * block_size
    for q in range(block_size):
        for h in range(q, -1, -block_step):
            nw[q] += window[h] ** 2
        for h in range(q + block_step, block_size, block_step):
            nw[q] += window[h] ** 2
    return [window[q] / math.sqrt(nw[q]) for q in range(block_size)]


# https://github.com/HomeOfVapourSynthEvolution/VapourSynth-DFTTest/blob/
# bc5e0186a7f309556f20a8e9502f2238e39179b8/DFTTest/DFTTest.cpp#L462
def get_window_value(location: float, size: int, mode: int, beta: float) -> float:
    temp = math.pi * location / size
    if mode == 0: # hanning
        return 0.5 * (1 - math.cos(2 * temp))
    elif mode == 1: # hamming
        return 0.53836 - 0.46164 * math.cos(2 * temp)
    elif mode == 2: # blackman
        return 0.42 - 0.5 * math.cos(2 * temp) + 0.08 * math.cos(4 * temp)
    elif mode == 3: # 4 term blackman-harris
        return (
            0.35875
            - 0.48829 * math.cos(2 * temp)
            + 0.14128 * math.cos(4 * temp)
            - 0.01168 * math.cos(6 * temp)
        )
    elif mode == 4: # kaiser-bessel
        def i0(p: float) -> float:
            p /= 2
            n = t = d = 1.0
            k = 1
            while True:
                n *= p
                d *= k
                v = n / d
                t += v * v
                k += 1
                if k >= 15 or v <= 1e-8:
                    break
            return t
        v = 2 * location / size - 1
        return i0(math.pi * beta * math.sqrt(1 - v * v)) / i0(math.pi * beta)
    elif mode == 5: # 7 term blackman-harris
        return (
            0.27105140069342415
            - 0.433297939234486060 * math.cos(2 * temp)
            + 0.218122999543110620 * math.cos(4 * temp)
            - 0.065925446388030898 * math.cos(6 * temp)
            + 0.010811742098372268 * math.cos(8 * temp)
            - 7.7658482522509342e-4 * math.cos(10 * temp)
            + 1.3887217350903198e-5 * math.cos(12 * temp)
        )
    elif mode == 6: # flat top
        return (
            0.2810639
            - 0.5208972 * math.cos(2 * temp)
            + 0.1980399 * math.cos(4 * temp)
        )
    elif mode == 7: # rectangular
        return 1.0
    elif mode == 8: # Bartlett
        return 1 - 2 * abs(location - size / 2) / size
    elif mode == 9: # bartlett-hann
        return 0.62 - 0.48 * (location / size - 0.5) - 0.38 * math.cos(2 * temp)
    elif mode == 10: # nuttall
        return (
            0.355768
            - 0.487396 * math.cos(2 * temp)
            + 0.144232 * math.cos(4 * temp)
            - 0.012604 * math.cos(6 * temp)
        )
    elif mode == 11: # blackman-nuttall
        return (
            0.3635819
            - 0.4891775 * math.cos(2 * temp)
            + 0.1365995 * math.cos(4 * temp)
            - 0.0106411 * math.cos(6 * temp)
        )
    else:
        raise ValueError("unknown window")


# https://github.com/HomeOfVapourSynthEvolution/VapourSynth-DFTTest/blob/
# bc5e0186a7f309556f20a8e9502f2238e39179b8/DFTTest/DFTTest.cpp#L461
def get_window(
    radius: int,
    block_size: int,
    block_step: int,
    spatial_window_mode: int,
    spatial_beta: float,
    temporal_window_mode: int,
    temporal_beta: float,
) -> typing.List[float]:

    temporal_window = [
        get_window_value(
            location = i + 0.5,
            size = 2 * radius + 1,
            mode = temporal_window_mode,
            beta = temporal_beta
        ) for i in range(2 * radius + 1)
    ]

    spatial_window = [
        get_window_value(
            location = i + 0.5,
            size = block_size,
            mode = spatial_window_mode,
            beta = spatial_beta
        ) for i in range(block_size)
    ]

    spatial_window = normalize(
        window=spatial_window,
        block_size=block_size,
        block_step=block_step
    )

    window = []
    for t_val in temporal_window:
        for s_val1 in spatial_window:
            for s_val2 in spatial_window:
                value = t_val * s_val1 * s_val2

                # normalize for unnormalized FFT implementation
                value /= math.sqrt(2 * radius + 1) * block_size

                window.append(value)

    return window


def get_sigma(
    position: float,
    length: int,
    func: typing.Callable[[float], float]
) -> float:

    if length == 1:
        return 1.0
    elif position > length // 2:
        return func((length - position) / (length // 2))
    else:
        return func(position / (length // 2))


def DFTTest2(
    clip: vs.VideoNode,
    ftype: int = 0,
    sigma: typing.Union[float, typing.Sequence[typing.Callable[[float], float]]] = 8.0,
    sigma2: float = 8.0,
    pmin: float = 0.0,
    pmax: float = 500.0,
    sbsize: int = 16,
    sosize: int = 12,
    tbsize: int = 3,
    swin: int = 0,
    twin: int = 7,
    sbeta: float = 2.5,
    tbeta: float = 2.5,
    zmean: bool = True,
    f0beta: float = 1.0,
    device_id: int = 0
) -> vs.VideoNode:
    """ this interface is not stable """

    if any((
        clip.format.sample_type != vs.FLOAT,
        clip.format.bits_per_sample != 32
    )):
        raise TypeError('"clip" must be of 32-bit float format')

    # translate parameters
    if ftype == 0:
        if abs(f0beta - 1) < 0.00005:
            filter_type = 0
        elif abs(f0beta - 0.5) < 0.0005:
            filter_type = 6
        else:
            filter_type = 5
    else:
        filter_type = ftype

    radius = (tbsize - 1) // 2
    block_size = sbsize
    block_step = sbsize - sosize
    spatial_window_mode = swin
    temporal_window_mode = twin
    spatial_beta = sbeta
    temporal_beta = tbeta
    zero_mean = zmean

    try:
        sigma_scalar = float(sigma) # type: ignore
        sigma_is_scalar = True
    except:
        # compute sigma_array

        sigma_is_scalar = False

        sigma_funcs = typing.cast(typing.Sequence[typing.Callable[[float], float]], sigma)
        if callable(sigma_funcs):
            sigma_funcs = [sigma_funcs]
        else:
            sigma_funcs = list(sigma_funcs)
        sigma_funcs.extend([sigma_funcs[-1]] * 3)
        sigma_func_x, sigma_func_y, sigma_func_t = sigma_funcs[:3]

        sigma_array = []

        for t in range(2 * radius + 1):
            sigma_t = get_sigma(position=t, length=2*radius+1, func=sigma_func_t)
            for y in range(block_size):
                sigma_y = get_sigma(position=y, length=block_size, func=sigma_func_y)
                for x in range(block_size // 2 + 1):
                    sigma_x = get_sigma(position=x, length=block_size, func=sigma_func_x)
                    sigma_array.append(sigma_t * sigma_y * sigma_x)

    window = get_window(
        radius=radius,
        block_size=block_size,
        block_step=block_step,
        spatial_window_mode=spatial_window_mode,
        temporal_window_mode=temporal_window_mode,
        spatial_beta=spatial_beta,
        temporal_beta=temporal_beta
    )

    wscale = math.fsum(w * w for w in window)

    if ftype < 2:
        if sigma_is_scalar:
            sigma_scalar *= wscale
        else:
            sigma_array = [s * wscale for s in sigma_array]
        sigma2 *= wscale

    pmin *= wscale
    pmax *= wscale

    if radius == 0:
        window_freq = core.dfttest2_cuda.RDFT(
            data=[w * 255 for w in window],
            shape=(block_size, block_size),
            device_id=device_id
        )
    else:
        window_freq = core.dfttest2_cuda.RDFT(
            data=[w * 255 for w in window],
            shape=(2 * radius + 1, block_size, block_size),
            device_id=device_id
        )

    kernel = Template(
    """
    #define FILTER_TYPE ${filter_type}
    #define ZERO_MEAN ${zero_mean}
    #define SIGMA_IS_SCALAR ${sigma_is_scalar}

    #if ZERO_MEAN
    __device__ static const float window_freq[] { ${window_freq} };
    #endif // ZERO_MEAN

    __device__ static const float window[] { ${window} };

    __device__
    static void filter(float2 & value, int x, int y, int t) {
    #if SIGMA_IS_SCALAR
        float sigma = static_cast<float>(${sigma});
    #else // SIGMA_IS_SCALAR
        __device__ static const float sigma_array[] { ${sigma} };
        float sigma = sigma_array[(t * BLOCK_SIZE + y) * (BLOCK_SIZE / 2 + 1) + x];
    #endif // SIGMA_IS_SCALAR
        [[maybe_unused]] float sigma2 = static_cast<float>(${sigma2});
        [[maybe_unused]] float pmin = static_cast<float>(${pmin});
        [[maybe_unused]] float pmax = static_cast<float>(${pmax});
        [[maybe_unused]] float multiplier {};

    #if FILTER_TYPE == 2
        value.x *= sigma;
        value.y *= sigma;
        return ;
    #endif

        float psd = (value.x * value.x + value.y * value.y) * (255.0f * 255.0f);

    #if FILTER_TYPE == 1
        if (psd < sigma) {
            value.x = 0.0f;
            value.y = 0.0f;
        }
        return ;
    #elif FILTER_TYPE == 0
        multiplier = fmaxf((psd - sigma) / (psd + 1e-15f), 0.0f);
    #elif FILTER_TYPE == 3
        if (psd >= pmin && psd <= pmax) {
            multiplier = sigma;
        } else {
            multiplier = sigma2;
        }
    #elif FILTER_TYPE == 4
        multiplier = sigma * sqrtf(psd * (pmax / ((psd + pmin) * (psd + pmax) + 1e-15f)));
    #elif FILTER_TYPE == 5
        multiplier = powf(fmaxf((psd - sigma) / (psd + 1e-15f), 0.0f), pmin);
    #else
        multiplier = sqrtf(fmaxf((psd - sigma) / (psd + 1e-15f), 0.0f));
    #endif

        value.x *= multiplier;
        value.y *= multiplier;
    }
    """
    ).substitute(
        sigma_is_scalar=int(sigma_is_scalar),
        sigma=(
            float(sigma_scalar)
            if sigma_is_scalar
            else ','.join(str(float(x)) for x in sigma_array)
        ),
        sigma2=float(sigma2),
        pmin=float(pmin),
        pmax=float(pmax),
        filter_type=int(filter_type),
        window_freq=','.join(str(float(x)) for x in window_freq),
        zero_mean=int(zero_mean),
        window=','.join(str(float(x)) for x in window),
    )

    return core.dfttest2_cuda.DFTTest(
        clip,
        kernel=kernel,
        block_size=block_size,
        radius=radius,
        block_step=block_step,
        device_id=device_id
    )


def to_func(
    data: typing.Optional[typing.Sequence[float]],
    norm: typing.Callable[[float], float],
    sigma: float
) -> typing.Callable[[float], float]:

    if data is None:
        return lambda _: norm(sigma)

    locations = data[::2]
    sigmas = data[1::2]
    packs = list(zip(locations, sigmas))
    packs = sorted(packs, key=lambda group: group[0])

    def func(x: float) -> float:
        length = len(packs)
        for i in range(length - 1):
            if x <= packs[i + 1][0]:
                weight = (x - packs[i][0]) / (packs[i + 1][0] - packs[i][0])
                return (1 - weight) * norm(packs[i][1]) + weight * norm(packs[i + 1][1])
        raise ValueError()

    return func


def DFTTest(
    clip: vs.VideoNode,
    ftype: int = 0,
    sigma: float = 8.0,
    sigma2: float = 8.0,
    pmin: float = 0.0,
    pmax: float = 500.0,
    sbsize: int = 16,
    sosize: int = 12,
    tbsize: int = 3,
    swin: int = 0,
    twin: int = 7,
    sbeta: float = 2.5,
    tbeta: float = 2.5,
    zmean: bool = True,
    f0beta: float = 1.0,
    slocation: typing.Optional[typing.Sequence[float]] = None,
    ssx: typing.Optional[typing.Sequence[float]] = None,
    ssy: typing.Optional[typing.Sequence[float]] = None,
    sst: typing.Optional[typing.Sequence[float]] = None,
    device_id: int = 0
) -> vs.VideoNode:
    """ smode=1, tmode=0, ssystem=0 """

    _sigma: typing.Union[float, typing.Sequence[typing.Callable[[float], float]]]

    def norm(x: float) -> float:
        if tbsize == 1:
            return math.sqrt(x)
        else:
            return x

    if slocation is not None:
        _sigma = [to_func(slocation, norm, sigma)] * 3
    elif any(ss is not None for ss in (ssx, ssy, sst)):
        _sigma = [to_func(ss, norm, sigma) for ss in (ssx, ssy, sst)]
    else:
        _sigma = sigma

    return DFTTest2(
        clip=clip,
        ftype=ftype,
        sigma=_sigma,
        sigma2=sigma2,
        pmin=pmin,
        pmax=pmax,
        sbsize=sbsize,
        sosize=sosize,
        tbsize=tbsize,
        swin=swin,
        twin=twin,
        sbeta=sbeta,
        tbeta=tbeta,
        zmean=zmean,
        f0beta=f0beta,
        device_id=device_id
    )
