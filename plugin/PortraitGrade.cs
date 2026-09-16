using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using UnityEngine;
using UnityEngine.Rendering.PostProcessing;

namespace CompetitiveRounds
{
    /// <summary>
    /// Portrait colour grade (portrait darkness fix, option C).
    ///
    /// Players see every character through MainCamera's post stack: the colour
    /// grading of the global Post_Main volume (HDR mode with ACES, post
    /// exposure, contrast, saturation, lift/gamma/gain). The portrait camera has
    /// no post stack, so the matte held the raw authored colours and every card
    /// showed the character far darker than the game does.
    ///
    /// The portrait's straight colour is graded through a FIXED 17x17x17 RGB
    /// table AFTER the #630 difference matte. Grading never writes alpha, only
    /// pixels with a > 0 are touched, and the lookup is integer trilinear, so the
    /// same matte bytes give the same graded bytes on every machine. The table is
    /// baked once from a real render through a camera carrying MainCamera's
    /// grade (`portrait:gradebake`) and pasted into the four constants below.
    /// Bloom, vignette and chromatic aberration are not reproduced.
    ///
    /// Until those constants hold a table that passes its length and digest
    /// check, carries the baked marker, and is the table RECIPE_GRADE_FNV
    /// (PortraitRender.cs) names, the table is an identity placeholder,
    /// GradeBaked is false and Upload refuses to send.
    ///
    /// GRADE_TABLE_MARKER exists only to be probed (#306): a build carries the
    /// UTF-16LE literal SCR_GRADE_TABLE=PLACEHOLDER until a bake is pasted, and
    /// SCR_GRADE_TABLE=BAKED after. No other code in the plugin holds either
    /// literal whole (MarkerBaked builds the second at run time), so a byte scan
    /// of the DLL tells the two builds apart.
    ///
    /// Table layout: 17 nodes per axis at byte values 0, 16, 32, ..., 240, 255
    /// (every node an exact integer). Node (ri, gi, bi) sits at offset
    /// ((ri * 17 + gi) * 17 + bi) * 3 and holds the graded R, G, B bytes of that
    /// input colour.
    /// </summary>
    internal static partial class PortraitRender
    {
        // ── the baked table: paste BepInEx/pc_grade_lut.cs.txt over these four,
        //    then set RECIPE_GRADE_FNV in PortraitRender.cs as that file says ──
        // baked 2026-09-15 02:12:23Z by portrait:gradebake on a build at RECIPE 2
        internal const string GRADE_TABLE_MARKER = "SCR_GRADE_TABLE=BAKED";
        internal const string GRADE_LUT_B64 =
            "AAEUAAEXAAEgAAAwAABJAABqAACOAACuAADIAADaAADoAADxAAD3AAD7AAD+AAD/AAD/AAQUAAUXAAQgAAMxAAFKAABrAACOAACu" +
            "AADIAADbAADoAADxAAD3AAD7AAD+AAD/AAD/ABATABAXABEgABAxAA1KAAhrAAKPAACvAADIAADbAADoAADxAAD3AAD7AAD+AAD/" +
            "AAD/ACcPACcUACgeACcwACZKACRrACCPABmvAA3IAAPbAAHoAADxAAD3AAD7AAD+AAD/AAD/AEcEAEcLAEcYAEgtAEhIAEdqAEaO" +
            "AEOuAD7IADXaACnoABjxAAr3AAD7AAD+AAD/AAD/AG4AAG8AAG8JAHAlAHFEAHFoAHGNAG+sAG7GAGnZAGPmAFrvAE31AD36ACv9" +
            "ABr/AAz/AJcAAJgAAJgAAJkUAJo9AJpkAJuKAJqqAJrEAJjWAJbjAJLsAIvyAIL3AHX6AGX9AFL/ALoAALoAALoAALsCALszALtf" +
            "ALyHALyoALzBALzUALvhALrqALfvALP0AK33AKX6AJn8ANIAANIAANIAANIAANImANNZANOEANOlANO/ANPSANPfANPoANLtANHy" +
            "AM/1AMz3AMj5AOIAAOIAAOIABOIAFeIVHuJTI+KAJeKjJOK+HuLRFOLeA+LmAOPsAOPwAOPzAOL1AOD3M+wANOsANusAOesAQ+sA" +
            "TOtLUOt8UuuiUeu9TevQRuvdPevlOOzrM+zvKO3yHe30D+32cPEAcfEAdPEAePEAffEAgfFAhPB4hfCfhvC7hvDPhfDcgfDlevDq" +
            "cPHuW/HxQ/LzKfL1mfQAmfQAm/QAnvQAofQAo/QzpfNxpvOcp/O6p/POpvPbpfPkovPqnfPulPPxivTzfvT0tPYRtPYRtfYRt/YR" +
            "ufYRu/UqvPVpvfWYvfW3vfXNvfXbvfXkvPXpu/Xut/XwsfXyqfX0x/cvyPcvyPcvyfcwy/cwzPc1zfZfzfaRzfa0zfbLzfbazfbj" +
            "zfbpzPbty/bwyPbyxPb01fdG1fhG1vdG1vhH1/dH2PdH2fdd2feL2Pew2PfJ2PfZ2Pfj2Pfp2Pft1/fw1vfy1ff03vhb3vhb3vhb" +
            "3/hb4Phb4Phc4fhj4fiE4Per4PfH3/fY3/fi3/fp3/ft3/fw3/fy3vfzAAEUAAEXAAEgAAAxAABKAABqAACOAACuAADIAADbAADo" +
            "AADxAAD3AAD7AAD+AAD/AAD/AAUUAAUXAAUgAAMxAAFKAABrAACOAACuAADIAADbAADoAADxAAD3AAD7AAD+AAD/AAD/ABETABEX" +
            "ABEgABAxAA5KAAlrAAOPAACvAADIAADbAADoAADxAAD3AAD7AAD+AAD/AAD/ACcPACgUACgeACgwACdKACVrACGPABqvAA7IAAPb" +
            "AAHoAADxAAD3AAD7AAD+AAD/AAD/AEcDAEcKAEgYAEgsAEhIAEhqAEaOAEOuAD7IADbaACroABnxAAv3AAD7AAD+AAD/AAD/AG8A" +
            "AG8AAG8JAHAlAHFEAHFoAHGMAHCtAG7GAGrZAGTmAFvvAE31AD36ACz9ABr/AA3/AJgAAJgAAJkAAJkTAJo9AJpkAJuKAJuqAJrD" +
            "AJjWAJbjAJLsAIvyAIP3AHX6AGb9AFP/ALoAALoAALoAALoCALszALtfALyHALyoALzBALzUALvhALrpALfvALP0AK33AKX6AJr8" +
            "ANIAANIAANIAANIAANImANNZANODANOlANO/ANPSANPfANPoANLtANHyAM/1AMz3AMj5CeIAEOIAGOIAIeIAKeIVLuJSMuKAM+Kj" +
            "MuK+L+LRKOLeGOLmC+LsAOLwAOLzAOL1AOD3POsAP+sARusATesAVesAW+tLX+t8YeuhYOu8XevQV+vdSuvlQevrOOzvMOzyJO30" +
            "FO32efEAevEAffEAgfEAhfEAifBAi/B4jfCfjfC7jfDPjPDciPDlgvDqevDuafHxU/HzMvL1nvQAn/QAoPQAo/QApvMAqPMzqfNx" +
            "qvOcq/O5q/POq/PbqvPkp/Pqo/Pum/PxkPTzhPT0t/YRuPURufYRuvURvPUSvvUqv/VpwPWYwPW3wPXNwPXbwPTkv/XqvvXuuvXx" +
            "tfXyrvX0yvcvyvcvy/cwzPcwzfcwzvc1z/Zfz/aRz/a0z/bLz/baz/bjzvbpzvbtzPbwyvbyx/b01vdG1/dG1/dH2PdH2fdH2vdI" +
            "2vdd2veL2vew2ffJ2ffZ2ffj2ffp2fbt2Pfw1/fy1vf03/hb3/hb3/hb4Phb4Phb4fhc4vhj4viE4fer4PfH4PfY4Pfi4Pfo4Pft" +
            "4Pfw3/fy3/fzAAIVAAEXAAEgAAAxAABKAABqAACOAACuAADIAADaAADoAADxAAD3AAD7AAD+AAD/AAD/AAUUAAUXAAUgAAQxAAFK" +
            "AABrAACOAACuAADIAADbAADoAADxAAD3AAD7AAD+AAD/AAD/ABESABEWABEfABExAA9KAAprAAOPAACvAADIAADbAADoAADxAAD3" +
            "AAD7AAD+AAD/AAD/ACgPACgUACgdACgwACdKACVrACKPABuvAA/IAATbAAHoAADxAAD3AAD7AAD+AAD/AAD/AEcDAEgKAEgXAEks" +
            "AElIAEhqAEeOAESuAD/IADfaACzoABvxAAz3AAD7AAD+AAD/AAD/AG8AAG8AAHAIAHAkAHFEAHFoAHGMAHCtAG7GAGrYAGXmAFzv" +
            "AE71AD/6AC39ABz/AA7/AJgAAJgAAJkAAJkTAJo9AJpkAJuKAJuqAJrDAJnWAJbjAJPsAIzyAIT3AHf6AGf9AFT/ALoAALoAALoA" +
            "ALsCALsyALtfALuGALyoALzBALvUALvhALrpALfvALT0AK73AKb6AJv8ANIAANIAANIAANIAANIlANJZANKDANOlANO/ANPSANPf" +
            "ANPnANLtANHxAND1AM33AMj5LuEAMOEANOEAOOEAPOEVQeFSQ+GAROGjQ+G+QuLRPuLeNuLmI+LsBeLwAuLzAOL1AOD3WusAXesA" +
            "YesAZusAa+sAcOtKc+t8dOqhdOq8c+rQburcZuvlVevrQevvOuzyLez0G+32h/AAifAAi/AAjvAAkvAAlfBAl/B4mPCfmPC7mPDP" +
            "l+/clfDlj/DqiPDue/DxZvHzQPH1pvMAp/MAqfMAq/MArfMAr/MysfNxsfObsvO5svLOsvLbsfLkr/Lqq/PupPPxmvPzjPT0vfUR" +
            "vfURvvURwPUSwfURw/UqxPVpxPWXxPW3xPTNxPTbxPTkw/TpwvTuwPTwu/XytvX0zfYwzvcwzvcwz/Yw0PYx0fY20vZf0vaR0va0" +
            "0vbL0fba0fXj0fXp0fXt0Pbwzfbyy/b02fdH2fdH2fdH2vdH2/dI3PdI3Pdd3PeL2/ew2/fJ2/bZ2/bj2/bp2/bt2vbw2vby2Pb0" +
            "4fhb4fhb4fhb4vhc4vhc4/hc5Phj4/eE4/er4vfH4ffY4ffi4ffo4fft4ffw4ffy4PfzEQAUEwAXFQAgFQAwDgBKAwBqAQCOAACu" +
            "AADIAADbAADoAADxAAD3AAD7AAD+AAD/AAD/FgQTFwQXGQQgGQIwFQBKBwBrAQCPAACvAADIAADbAADoAADxAAD3AAD7AAD+AAD/" +
            "AAD/GhARHBAVHhAfHxAwHA1KEQhrAwKPAQCvAADIAADbAADoAADxAAD3AAD7AAD+AAD/AAD/HigOICgTIigcIycvIidKGiVrCiGP" +
            "AhuvABHIAAbbAAHoAADxAAD3AAD7AAD+AAD/AAD/F0gCGkgIHkkXIUksIUlIG0hqDUeOBESuAT/HADjaAC7oAB7xAA/3AAD7AAD+" +
            "AAD/AAD/B28ACHAACXAHEHEjE3FED3JoCXGMBnCsAm7FAGvYAGbmAF7vAFH1AEL6AC/9AB3/AA//A5gABJgABpkACJkSCpo8C5tk" +
            "CpuJB5uqAprDAJjWAJbjAJPsAI3yAIX3AHj6AGn9AFb/BLoABrkACLoACroCDboxEbteEruGDrunCrvBBbvTArrgALnpALfvALT0" +
            "AK/3AKf6AJ38ItEAJtEALNEAMtEAONIkPtJYQNKDP9KlPNK/NtLSKtLfEtLnBdLtANHxAM/0AM33AMn5UeEAVOAAWOEAXeEAY+EU" +
            "Z+FSauGAa+GjaeG+ZeHQX+HdU+HmSOHsO+HwIeHzBuH1AuD3euoAe+oAfuoAgeoAheoAiepKi+p8jOqhjOq8i+rPierchOrleurr" +
            "bervVOvyP+v0Muz2mvAAm/AAnPAAn/AAovAApO8/pu93p++fp++7p+/Ppu/cpe/loe/qm+/ukvDxgvDza/H1s/MAs/MAtPMAtvMA" +
            "uPMAuvMyu/Jwu/Kbu/K5u/LOu/Lbu/LkufLqtvLusvLxqvPzn/P0xfUSxfUSxvUSx/USyfUSyvUqy/VpyvWXyvS3yvTNyvTbyvTk" +
            "yvTpyfTtx/TwxPTyv/T00vYx0/Yx0/Yx1PYx1fYy1vY21/Zf1vaR1va01fXL1fXa1fXj1fXp1fXt1PXw0vXy0PX03PdI3PdI3fdI" +
            "3fdI3vdI3/dJ3/dd3/eK3vew3vbJ3vbZ3vbj3vbp3fbt3fbw3Pby2/b04/dc4/hc5Phc5Phc5Phc5fhd5vdk5veE5Per5PfH4/fY" +
            "4/fi4/fo4/ft4/fw4/fy4vfzMgATNQAWOAAfOQAvOQBJNABqKgCOFACuAADIAADbAADoAADxAAD3AAD7AAD+AAD/AAD/NgETOAEW" +
            "OwAfPgAwPgBJOgBqMQCOHwCuCQDIAADbAADoAADxAAD3AAD7AAD+AAD/AAD/Ow0RPA0VPwweRAkvRQZKQgJrOwCPLQCvGADIAADb" +
            "AADoAADxAAD3AAD7AAD+AAD/AAD/RCYMRSYSRyYcSCYuTSVJTCNqRh6OPBeuKwzIFgPbAAHoAADxAAD3AAD7AAD+AAD/AAD/SkcB" +
            "TEcGT0gVUUgrU0hHVEhqUEaOSEOtPD7HKDfaBi7nAR/xABD3AAD7AAD+AAD/AAD/S3AATXAAUHAFVHEiV3FDWHFnVnGMUHCsRm7F" +
            "NmrYIGXlB17uAFL1AET6ADH9AB//ABH/SpgATJgAUJkAVJkRWJk7WppjWpqJVpqqT5nDQpjWMJbjDZPrAI3yAIb2AHr6AGv9AFn/" +
            "ULkAU7kAVrkAW7kCYLowY7peZLqGY7unXrrBVrrTSbngM7jpHbbvALTzAK/3AKj5AJ78ZNAAZtAAadEAbdAActEjddFYd9GDd9Gl" +
            "ddG/cdHSatHeXtHnTNDtNtDxHc70AMz3AMn5fuAAgOAAguAAhuAAieASjOBRjuB/juCjjuC9jODQieDdg+DmeODrauDwVeDzP+D1" +
            "Jd/3l+kAmOkAmukAnekAoOkAoulJo+l7pOmhpOm8pOnPo+ncoOnlm+nrk+nvherycur0V+r1ru8Aru8AsO8Asu8AtO8Ate8+tu93" +
            "t++et+67t+7Pt+7ctu7ls+7qsO7uqu/xoO/zku/1wPIAwPIAwfIAwvIAxPIAxfIxxvJwxvKbxvK5xvHOxvHbxfHkxPHqw/HuwPHx" +
            "u/LztPL0zvUSzvUSzvQS0PUT0fQS0vQq0vRo0vSX0vS30fTM0fTa0fTk0fTp0PTtz/TwzfTyyvT02fYy2fYy2fYy2vYy2vYz2/Y3" +
            "3PZf2/WQ2/W02vXL2vXa2vXj2vXp2vXt2fXw2PXy1/X04PdJ4fdJ4fdJ4fdJ4vdJ4/dK4/dd4/eK4vaw4fbJ4fbZ4fbj4Pbp4Pbt" +
            "4Pbw4Pby3/b05vdd5vdd5/dd5/dd5/dd6Pde6Pdk6PeD5/eq5vfH5vfY5vfi5ffo5fft5ffw5ffy5ffzVgARWAAVWwAdYQAuZgBI" +
            "ZgBpYwCNXACtUQDHQADaLADoGQDxCwD2AAD7AAD+AAD/AAD/WQARWwAUXgAdZAAvagBIawBqaQCOYgCtWADHRgDaMQDoIADxEQD3" +
            "AAD7AAD+AAD/AAD/XwQPYQQTYwMcaQAubwBJcQBqcACOawCuYwDHVADaPwDoLADxGAD2AAD7AAD+AAD/AAD/aiIKayIPbCIabyIt" +
            "dh9IehpqehWOdguucATHZQHaVQDoPADwJAD2BwD7AwD+AAD/AAD/dkUBd0YEeUYTe0cqe0dGgUZpg0ONgUCtfDvGdDPZaCjnVRjw" +
            "Pwv2JwD7FAD+AAD/AAD/fW8Af28AgXAChHAhhnFCh3FmiXCLiG+rhGzFf2nXdWTlZ1zuUVH0N0P5IDL9BSD/AhH/gZgAgpgAhZgA" +
            "h5kPi5k6jZlijZmJjZmpi5jChpfVf5XidJHrX4zxR4X2MXv6HG39Dlv/h7gAiLgAirgAjbkBkLkvk7pdlLqFlLqnkrrAj7nTi7jg" +
            "grfpc7XuYbLzRq72Laj5GZ/7ktAAk9AAldAAmNAAm9AhndBXntCCntCkntC/nNDRmdDelNDni8/sfs7xaM30UMv2Nsj4od8Aot8A" +
            "pN8Apt8AqN8Rqt9Qq99/rN+irN+9q9/Qqt/dp9/mod/rmt/wjN7yet71Y972sekAsukAs+gAtekAt+gAuOhIueh7ueihuui8uejP" +
            "uOjct+jltejqsejvqujxnuj0jOj1wO4Awe4Awe4Aw+4AxO4Axe49xu52xu6exu67xu7Oxu7cxe7kxO7qwu7uvu7xue7zse70zfIA" +
            "zfIAzvIAz/IA0PIA0fIw0fFv0fGb0PG50PHN0PHb0PHkz/HqzvHuzPHxyfHzxfH01/QT1/QT2PQT2PQU2fQU2vQq2vRn2vSW2fS3" +
            "2fTM2fPa2PPj2PPp2PPt1/Pw1fPy1PT03/Y03/U03/U04PU04PU14fU54fVe4fWQ4PW03/XL3/Xa3/Xj3/Xp3/Xt3vXw3vXy3fX0" +
            "5fdK5fdK5fdL5vdL5vdL5/dM5/de5/aJ5vav5fbJ5fbZ5Pbi5Pbp5Pbt5Pbw5Pby4/b06fde6vde6vde6vde6vdf6/df6/dl6/eD" +
            "6veq6ffH6PfY6Pfi6Pbo6Pft6Pfw6Pfy5/bzfwAPgQAThAAciQAtkQBHlwBpmACMlgCtkgDGiwDZgADnbwDwWgD2QwD6JQD+AAD/" +
            "AAD/gwAOhAAShwAcjAAtlABHmgBpnACNmwCtlgDGkADZhQDmdgDwYQD2SQD6KQD+AAD/AAD/iAAMigARjAAbkAAtmABInwBpogCN" +
            "oQCtngDHmADZjwDngADvbAD2UwD6LwD9AAD/AAD/khkGkxkMlBoYlxksnBVHpA1pqQaNqQOtpwHGogDZnADmkADvfAD1ZAD6RQD9" +
            "JgD/FQD/nkMAn0MCoUQQoUUookVFqENorj+MsDusrzXGrCvYpx7moAnvkQL1fwD6YwD9RgD/KgD/qG4AqW4Aqm8ArG8erHBBrHBl" +
            "sW+LtG2rs2vEsWbXrmHkqVntn0zzkj74ei78YB//PxD/rJcArZcArpgAsJgMspg4s5lhtJmItZiptZjCtJbVspTirpDqporxnIP1" +
            "inj5dGv8WVr+r7gAsLgAsbgAs7gBtbgtt7lcuLmFuLmmuLnAt7jTtbffsrborbTupbHzl6z2hab5bJ37tc8Ats8At88Auc8Aus8f" +
            "vM9Wvc+BvdCkvdC+vM/Ru8/euc7ntc7ssM3xpsv0l8n2g8b4vd4Avt4Av94AwN4Awt4Ow95PxN5+xN6ixN69w97Qw97dwt7lv97r" +
            "vN3vtt3yrNz1ntv2x+gAx+gAyOgAyegAy+gAy+hGzOh6zOigy+e7y+jPy+fcyuflyefqx+fvxOfxvuf0t+f10O0A0O0A0e0A0u0A" +
            "0+0A1O071O110+2e0+260+3O0+3b0u3k0u3q0e3uz+3xzO3zyO302PEA2PEA2fEA2vEA2/EA2/Ev2/Fu2/Ga2vG42vHN2vHb2fHk" +
            "2fDp2fHu1/Dw1vHz1PH03/QU3/QU4PQV4PQV4fQU4fQp4fNm4POW4PO23/PM3/Pa3/Pj3/Pp3/Pt3vPw3fPy3PP05fU15fU25fU2" +
            "5vU25vU25/U65/Ve5vWP5fWz5PXL5PXa5PXj5PTp5PTt4/Xw4/Ty4vX06fZM6vZM6vZM6vZN6vZN6/ZN6/Ze6vaJ6fav6fbJ6PbZ" +
            "6Pbi6Pbp6Pbt5/bw5/by5/Xz7fdg7fdg7fdg7fdg7fdg7vdh7vdm7veD7Pep7PfG6/fY6vbi6/fo6vbt6vbw6vby6vbzqgAMqwAQ" +
            "rQAasQAstwBGvwBoxACMxQCsxADFwQDYvADmtgDvqQD0mgD5gwD8ZwD/QQD/rQALrgAQsAAaswAsuQBHwQBoxgCMxwCsxgDGxADY" +
            "wADmuQDvrgD1nwD5iAD8bAD/RAD/sQAIsgAOtAAZtwArvABHwwBoygCMywCsywDGyQDZxQDmvwDvtQD0pwD5kAD8dQD/UQD/uAwC" +
            "uQwIugwVvQwqwAlGxgRozQKM0AGs0ADGzwDZzQDmyADuvwD0tAD5nwD8hgD+ZwD/wUAAwkEBw0ELxEIlxUJEyUFnzzyM1Das1C7F" +
            "1CTY0xTl0APuywD0wgD4sgD8nQD+gQD/yW0AyW4Aym4Ay28ay3A/y3Bkzm+K02yq1WnE1mXW1V/k01bs0Ejyyzf3wir7shz+mw7/" +
            "zJcAzJcAzZgAzpgI0Jg30Jlgz5mH0Zmo05fC1JbU05Ph0o/q0InwzYL1x3X4vGj7rVj+zbcAzbcAzrgA0LgB0bgr0rhb0bmE0bmm" +
            "0bnA0rjS0rff0bboz7PuzbDyyKv1wKT4tZz6z84Az84A0M4A0c4A0s8c089U08+B08+k08++0s/R0s7e0s7n0M3szszxy8rzxcf2" +
            "vMT40t0A090A090A1N0A1d4K1t5N1t591t6i1t691d7Q1d3d1d3l093r0t3v0Nzyy9v0xtr21+cA2OcA2OcA2ecA2ucA2udF2ud5" +
            "2ueg2ee72efP2efc2efl2Ofq1+fu1efx0+bz0Ob13e0A3e0A3e0A3u0A3+0A3+043+103u2d3u263e3O3e3b3e3k3e3q3Ozu2+3x" +
            "2uzz1+z04vEC4vED4vED4/ED5PEE5PEt5PFt4/GZ4vC44vDN4fDb4fDk4fDq4PDt4PDx3/Dy3vD05vMX5/MY5/MY5/MY6PMZ6PMq" +
            "6PNl5/OV5vO25fPM5fPa5fPj5fPp5fPt5PPw5PPy4/P06vU46vU46/U56/U56/U57PU96/Vd6/WO6vWz6fXL6PTa6PTj6PTp6PTt" +
            "6PTw5/Ty5/T07fZP7fZP7fZP7vZP7vZQ7vZQ7vZe7vaI7fau7PbI6/bZ6/bi6/Xp6/Xt6/Xw6vXy6vX08Pdi8Pdi8Pdi8Pdi8Pdi" +
            "8fdj8fdo8PeC7/ep7vfG7fbX7fbi7fbo7fbt7fbw7fby7Pbz0AAI0QAN0wAX1QAq2ABF3gBn4wCL5wCr5wDF5gDY5QDl4gDu3QD0" +
            "1wD4ywD7uwD+pQD/0gAG0wAM1AAX1wAq2gBF3wBn5QCL6ACs6QDF6ADY5wDl5ADu3wD02QD4zgD7vwD+qQD/1QAD1gAJ1wAW2QAp" +
            "3ABF4ABn5gCM6gCs6wDF6wDY6gDl6ADu4wD03gD41AD7xQD+sAD/2QQA2gQD2wQR3QQn3wRE4gNn6AGL7ACs7gDF7gDY7gDl7ADu" +
            "6QD05AD43AD7zgD9vAD/3j4A3z8A3z8F4EAi4kBC5D9m6DuL7DSr7yvF8B7X8Ark8ALt7gDz6wD45QD72wD9zAD/4m4A4m4A428A" +
            "43AW5HE95HFj5XCJ6W2p7WrD7mXW71/j71Xs70by7jT36yf65Rr82w3+45cA45gA5JgA5JkE5Zk05Jpe5JqG5Jmn55jB6pbU6pPh" +
            "6pDq6orw6oL06XX45mf64lb94rcA4rgA47gA5LgB5Lgo5LlZ47mD4rml47m/5LjS5rff5bbo5bPt5bDy5Kv14qT435v64c4A4s4A" +
            "4s4A484A484X5M9T48+A4s+j4s++4s/Q4s7e4s7m4s3s4czw4Mrz3sf23MT34t0A4t0A4t0A490A5N0F5N1L5N18492h49284t3Q" +
            "4t3d4t3l4t3r4dzv4Nzy39v03Nr25OcA5OcA5OcA5ecA5ecA5udC5ed45eef5Oe75OfP4+fc4+fl4+bq4ubu4ubx4Obz3+X15+wA" +
            "5+wA5+0A5+0A6O0A6O026Oxz5+yc5uy65uzO5ezb5ezk5ezq5ezu5Ozx4+zz4uz06vAJ6vAJ6vAJ6vAK6/AL6/At6vBr6fCY6fC4" +
            "6PDN6PDb5/Dk5/Dp5/Du5/Dx5vDy5vD07PMe7PMe7PMe7fMf7fMf7fMt7fNj7POU6/O26vPM6vPa6vLj6fLp6fPt6fLw6fLy6PL0" +
            "7/U87/U87/U87/U88PU98PVA8PVd7/SN7vSy7PTK7PTZ7PTj7PTp6/Tt6/Tw6/Ty6/T08fZR8fZR8fZR8fZS8fZS8fZT8fZf8faH" +
            "8Pat7/XI7vXY7vXi7fXp7fXt7fXw7fXy7fXz8vdk8vdk8/dk8/dk8/dk8/dl8/dp8/eC8veo8fbF8PbX7/bi7/bo7/bt7/bw7/by" +
            "7/bz7gAD7wAI8AAU8QAo8wBD9gBm+gCL/QCr/wDF/wDX/wDl/gDt/ADz+gD39QD67wD95gD+7wAC8AAG8QAT8gAn9ABD9wBm+gCL" +
            "/gCr/wDF/wDY/wDl/wDt/QDz+wD39wD68QD96AD+8QAB8QAE8gAR9AAn9gBD+ABm+wCL/wCr/wDF/wDY/wDl/wDt/wDz/QD3+QD6" +
            "9AD97AD+8wMA9AMB9AML9QMk9wNC+QNm+wGL/wCr/wDF/wDY/wDl/wDt/wDz/wD3/QD6+AD98QD+9T4A9T4A9j8B9kAe90A/+D9k" +
            "+jyK/jaq/y3E/x/X/wjk/wHt/wDz/wD3/wD6/gD8+AD+9XAA9XAA9nEA9nEP9nI69nNh93KI+XCp/GzD/mfW/2Dj/1fr/0jy/zb2" +
            "/yn6/xv8/w7+85kA85kA9JoA9JoC9Jsw9Jxc85yF85yn9ZrB95jU+ZXh+pHq+ovv+4T0/Hf3/Wn6/Vj88bgA8bgA8bkA8bkA8boj" +
            "8bpX8LqC77qk77q/8LnS8rjf87bo87Tt87Hy9Kz19KX39Zz57s4A7s4A784A784A788S789R7s9+7c+i7M+97M/Q7c/d7s7m7s3s" +
            "7szw7srz7sf17cT37d0A7d0A7d0A7t0A7t0B7t1J7d177d2g7N68697P6t3c693l693r69zv69vy6tv06tn17eYA7eYA7eYA7ucA" +
            "7ucA7uc/7ed37eee7Oe66+bO6+fc6ubk6ubq6ubu6ubx6ubz6eX17uwA7uwA7uwA7+wA7+wA7+wy7uxx7eyb7Oy57OzN6+zb6+zk" +
            "6+zq6+zu6+zx6uzz6uz08PAR8PAR8PAR8PAS8PAS8PAs8PBp7/CX7vC37fDN7fDa7PDj7PDp7PDu7PDw7PDy6+/08fMk8fMk8fMl" +
            "8fMm8vMm8vMw8fNh8POT7/O17vLL7vLa7fLj7fLp7fLt7fLw7fLy7fL08vVA8vRA8/VA8/VB8/VB8/VD8/Rc8vSL8fSx8PTK7/TZ" +
            "7/Tj7/Tp7/Tt7vTw7vTy7vTz9PZV9PZV9PZV9PZV9PZW9PZW9PZg9PaF8vWt8fXI8fXY8PXi8PXo8PXt8PXw8PXy8PXz9fdn9fdn" +
            "9fdn9fdn9fdn9fdo9fdr9feB9Pan8/bF8vbX8fbi8fbo8fbt8fbw8fby8fbz/wAB/wAD/wAP/wAl/wBC/wBk/wCK/wCq/wDE/wDX" +
            "/wDk/wDt/wDz/wD3/wD6/wD8/wD+/wAA/wAC/wAO/wAl/wBB/wBl/wCK/wCq/wDE/wDX/wDk/wDt/wDz/wD3/wD6/wD8/wD+/wAA" +
            "/wAA/wAL/wAj/wBB/wBk/wCK/wCr/wDE/wDX/wDk/wDt/wDz/wD3/wD6/wD8/wD+/wMA/wMA/wMF/wMg/wNA/wNk/wKJ/wGq/wDE" +
            "/wDX/wDk/wDt/wDz/wD3/wD6/wD8/wD+/0AA/0AA/0EA/0IY/0I8/0Ji/0CI/zup/zLD/yTX/xDk/wPt/wDz/wD3/wD6/wD8/wD+" +
            "/3IA/3MA/3QA/3QI/3U2/3Vf/3WG/3So/3DC/2vV/2Ti/1vr/0zx/zv2/yz5/x78/xD9/5sA/5wA/5wA/50B/50r/p5a/p6D/p6l" +
            "/p3A/5rT/5fg/5Tp/47v/4b0/3v3/236/1z8+7kA+7oA+7oA+7oA+7sd+rtU+byA+Lyj+Ly++LvR+rne+7jn/LXt/bLx/q30/6f3" +
            "/575988A988A988A+M8A+NAM99BN9tB99dCh9NC989DQ9NDd9c/m9s7s9s3w98vz98j198X39d0A9d0A9d0A9d0A9d0A9d5G9N55" +
            "896f8t678d7P8d7c8d3l8t3r8t3v8tzy8tv08tr19OYA9OYA9OYA9OYA9OcA9Oc89Od18ued8ee68ebO8Ofb7+fk8Obq8Obu8Obx" +
            "8OXz8OX19OwA9OwA9OwA9OwA9OwA9Owt8+xv8uya8ey48ezN8Ozb8Ozk7+zq7+zu7+zx7+zz7+z09PAX9PAY9PAY9PAY9fAZ9fAr" +
            "9PBn8/CW8vC38fDM8PDa8PDj8PDp8PDt8O/w8O/y8O/09fIr9fMr9fMr9fMs9fMs9fMz9fNf9POR8vK08fLL8fLa8fLj8PLp8PLt" +
            "8PLw8PLy8PL09fRE9fRE9vRE9vRF9vRF9vRH9vRb9fSK9PSx8vTJ8vTZ8fTj8fTp8fTt8fTw8fTy8fT09vZY9vZZ9vZY9vZZ9vZZ" +
            "9/ZZ9/Zh9vWE9fWs8/XH8/XY8vXi8vXo8vXt8vXw8vXy8vXz9/dq9/Zq9/Zq9/Zq9/dr9/Zr9/dt9/aA9vam9PbE9PbX8/bh8/bo" +
            "8/bt8vbw8vby8vbz/wAC/wAD/wAJ/wAh/wA//wBj/wCI/wCq/wDE/wDX/wDk/wDt/wDz/wD3/wD6/wD8/wD9/wAC/wAC/wAH/wAg" +
            "/wA//wBj/wCJ/wCq/wDE/wDX/wDk/wDt/wDz/wD3/wD6/wD8/wD9/wAA/wAA/wAE/wAf/wA+/wBj/wCI/wCq/wDE/wDX/wDk/wDt" +
            "/wDz/wD3/wD6/wD8/wD+/wQA/wQA/wQB/wQb/wQ9/wRi/wOI/wGp/wDE/wDX/wDk/wDt/wDz/wD3/wD6/wD8/wD+/0QA/0QA/0UA" +
            "/0YQ/0c4/0dg/0WH/0Go/zrD/y7W/xzk/wXs/wDy/wD3/wD6/wD8/wD9/3YA/3cA/3cA/3gD/3kx/3lc/3mF/3in/3XB/3DU/2ni" +
            "/2Dr/1Lx/0L1/zP5/yP7/xL9/54A/58A/58A/58A/6Al/6FX/6GB/6Gk/6C//57S/5vg/5fp/5Hv/4rz/3/3/3H5/2H7/7wA/7sA" +
            "/7wA/7wA/70V/71R/71+/76i/r69/r3R/7ze/7rn/7ft/7Tx/7D0/6n3/6H5/dAA/dAA/dAA/dAA/dAE/dFK/NF7+9Gg+dG8+dHP" +
            "+dHd+tDm+8/r+87w/Mzz/cn1/cb3+t0A+t4A+t4A+t4A+t4A+t5B+d53+N6e99669t7O9d7c9d7l9t3q993v99zy99v099r1+eYA" +
            "+eYA+ecA+ecA+ecA+ec3+Odz9+ec9ee59efN9Ofb8+fk9Ofq9Obu9Obx9Obz9OX1+OwA+OwA+OwA+OwA+OwA+Owq9+xt9uyZ9ey4" +
            "9OzN9Ozb8+zk8+zq8uzu8+zx8+zz8+z0+PAe+PAe+PAe+PAf+PAf+PAs9/Bk9vCV9fC29PDM8/Da8/Dj8/Dp8vDt8u/w8/Dy8u/0" +
            "+PMy+PMy+PMz+PIz+PMz+PM2+PNc9vKQ9fKz9PLL9PLa8/Lj8/Lp8/Lt8vLw8vLy8vL0+PRJ+PRJ+PRK+PRK+PRK+PRL+PRa9/SI" +
            "9vSv9fTJ9PTZ8/Ti8/Tp8/Tt8/Tw8/Ty8/Tz+PZc+PVc+PZc+PVd+PVd+PVd+PVh+PWC9vWr9fXG9PXY9PXi9PXo8/Xt8/Xw8/Xy" +
            "8/Xz+PZt+PZt+PZt+PZu+PZu+fZu+fZw+PZ/9/ak9vbE9fbW9Pbh9Pbo9Pbt9Pbw9Pby9Pbz/wAG/wAG/wAJ/wAc/wA8/wBg/wCH" +
            "/wCo/wDD/wDX/wDk/wDt/wDz/wD3/wD6/wD8/wD9/wAG/wAG/wAI/wAb/wA7/wBg/wCH/wCp/wDD/wDX/wDk/wDt/wDy/wD3/wD6" +
            "/wD8/wD9/wAE/wAE/wAF/wAZ/wA7/wBg/wCH/wCo/wDD/wDX/wDk/wDt/wDz/wD3/wD6/wD8/wD9/wYA/wYA/wYA/wcT/wc4/wdf" +
            "/waG/wSo/wLD/wHX/wDk/wDt/wDz/wD3/wD6/wD8/wD9/0oA/0sA/0wA/00I/04z/05c/02F/0qn/0TC/zrV/yvj/xHs/wTy/wD3" +
            "/wD6/wD8/wD9/3sA/3wA/3wA/30B/34q/35Y/36C/32l/3vA/3fU/3Hh/2fq/1rx/0v1/zn5/yf7/xX9/6IA/6IA/6IA/6MA/6Md" +
            "/6RS/6R//6Sj/6O+/6LS/5/f/5vp/5Xv/4/z/4T2/3f5/2b7/74A/74A/74A/74A/78L/79M/8B7/8Ch/7+8/7/Q/77e/7zn/7ns" +
            "/7fx/7P0/633/6X4/9EA/9EA/9EA/9IA/9IB/9JE/9J4/tKe/dK7/NLP/NLc/dHl/tDr/s/w/83z/8v1/8j2/t4A/t4A/t4A/t4A" +
            "/t8A/t87/d90+9+c+t+5+d/O+N/b+N/l+d7q+t7v+t3x+tz0+9v1/OcB/OcB/OcB/OcB/OcC/Ocx++dv+uea+Oe49+fN9+fb9ufk" +
            "9ufq9+fu9+bx9+bz9+b1++wE++wE++wF++wF++wG++wo+uxp+eyX+Oy39+zM9uza9ezk9ezp9ezu9ezx9ezz9uz0+vAl+vAl+vAm" +
            "+vAm+vAn+vAw+vBh+PCT9/C19vDL9vDa9fDj9fDp9PDt9O/w9e/y9e/0+vI6+vM6+vI6+vI6+vM7+vM8+vNb+PKN9/Ky9vLK9fLZ" +
            "9fLj9fLp9PLt9PLw9PLy9PL0+vRP+vRP+vRP+vRP+vRQ+vRR+vRb+fSG9/Su9vTI9vTY9fTi9fTp9fTt9PTw9PTy9PT0+vVh+vVh" +
            "+vVh+vVh+vVi+vVi+vVk+fWB+PWp9/XG9vXX9fXi9fXo9fXt9fXw9fXy9fXz+vZx+vZx+vZx+vZx+vZy+vZy+vZz+vZ/+Paj9/bD" +
            "9vbW9vbh9fbo9fbs9fbw9fby9fbz/wAM/wAM/wAM/wAX/wA4/wBe/wCF/wCo/wDD/wDW/wDk/wDt/wDy/wD3/wD6/wD8/wD9/wAL" +
            "/wAL/wAL/wAW/wA3/wBd/wCF/wCn/wDD/wDW/wDk/wDs/wDy/wD3/wD6/wD8/wD9/wAJ/wAJ/wAI/wAU/wA2/wBd/wCF/wCn/wDC" +
            "/wDW/wDk/wDt/wDy/wD3/wD6/wD8/wD9/wsC/wsC/wwC/w4L/w4z/w5c/wyE/wmn/wXC/wLW/wHk/wDt/wDy/wD3/wD6/wD8/wD9" +
            "/1EA/1EA/1IA/1QC/1Qt/1RZ/1SC/1Gm/0zB/0TV/zfj/x/s/w7y/wD2/wD6/wD8/wD9/4AA/4AA/4EA/4IA/4Mj/4NU/4OA/4Kk" +
            "/4C//33T/3jh/2/q/2Lw/1P1/0D4/yz7/xr9/6UA/6UA/6YA/6YA/6cT/6hO/6h8/6ih/6e9/6bR/6Pf/6Do/5ru/5Tz/4r2/335" +
            "/2z7/8AA/8AA/8AA/8EA/8ED/8FG/8J4/8Kf/8K7/8HQ/8Dd/7/m/7zs/7nx/7X0/7D2/6n4/9IA/9IA/9IA/9MA/9MA/9M+/9N1" +
            "/9Sd/9S6/9TO/9Pc/9Pl/9Lr/9Dw/8/y/8z1/8r2/98A/98A/98A/98A/98A/980/99x/t+a/eC4/N/N+9/b+9/k+9/q/N7v/N7x" +
            "/d30/dz1/ucD/ucD/ucD/ucE/ucE/ucr/eds/OeY++e3+ufM+efa+Ofk+Ofq+Ofu+efx+ebz+eb0/ewO/ewP/ewP/ewQ/ewR/ewo" +
            "/O1m++yV+uy2+ezM+Oza9+zj9+zp9+zt9+zw9+zz9+z0/PAt/PAt/PAt/PAt/PAu/PA0/PBf+/CR+fC0+PDL9/Da9/Dj9vDp9vDt" +
            "9vDw9vDy9u/0/PJB/PJB/PJB/PJB/PJC/PNC+/Jb+vKL+fKx+PLJ9/LZ9/Li9vLp9vLt9vLw9vLy9vL0+/RU+/RU+/RV+/RV+/RV" +
            "+/RW+/Rd+vSE+fSt+PTI9/TY9/Ti9vTo9vTt9vTw9vTy9vTz+/Vm+/Vm+/Vm+/Vm+/Vm+/Vn+/Vn+vWA+fWo+PXF9/XX9vXh9vXo" +
            "9vXt9vXw9vXy9vXz+/Z1+/Z1+/Z1+/Z1+/Z2+/Z2+/Z2+/aA+vai+PbC9/bW9/bh9vbo9vbs9vbv9vby9vbz/wAT/wAT/wAT/wAW" +
            "/wAy/wBa/wCC/wCm/wDC/wDW/wDk/wDs/wDy/wD3/wD6/wD7/wD9/wAS/wAS/wAS/wAW/wAx/wBa/wCC/wCm/wDC/wDW/wDj/wDs" +
            "/wDy/wD3/wD6/wD8/wD9/wAQ/wAQ/wAQ/wAT/wAv/wBZ/wCC/wCm/wDB/wDW/wDk/wDs/wDy/wD3/wD5/wD8/wD9/xUJ/xcJ/xkK" +
            "/xsM/x0s/x1X/xmB/xKl/wvB/wbV/wPj/wHs/wDy/wD3/wD5/wD7/wD9/1kB/1kB/1oB/1sC/1wk/11U/1x//1qk/1fA/1DU/0Xi" +
            "/zTr/x/x/wD2/wD5/wD8/wD9/4YA/4YA/4cA/4gA/4gX/4lO/4l8/4ih/4e+/4TS/3/g/3jq/2zw/171/0f4/zH7/yD8/6kA/6kA" +
            "/6oA/6oA/6sH/6tH/6t4/6uf/6u8/6rQ/6je/6Xo/6Du/5ny/5D2/4P4/3P6/8IA/8IA/8MA/8MA/8MB/8Q//8R0/8Sc/8S6/8TP" +
            "/8Pd/8Lm/8Ds/73x/7n0/7T2/634/9QA/9QA/9QA/9QA/9QA/9U1/9Vw/9Wa/9W4/9XN/9Xc/9Tl/9Pr/9Lv/9Dy/870/8z2/+AA" +
            "/+AA/+AA/+AA/+AA/+As/+Bs/+CY/+C3/uDN/eDb/eDk/eDq/d/u/t/x/t70/931/+gJ/+gJ/+gK/+gK/+gK/+gn/+hn/uiV/Oi2" +
            "++jM+uja+ujj+ujq+uju+ufx++fz++b0/uwe/u0f/u0f/u0f/u0g/u0q/u1g/O2S++20+u3L+e3a+e3j+O3p+O3t+Ozw+ezy+ez0" +
            "/vA2/vA2/vA3/vA3/vA4/vA6/fBc/PCN+/Cy+fDK+fDZ+PDj+PDp9/Dt9/Dw9/Dy+PD0/fJI/fJI/fNJ/fNJ/fJJ/fJK/fJb/PKI" +
            "+vKv+fLI+PLY+PLi9/Lp9/Lt9/Lw9/Ly9/Lz/PRb/PRb/PRb/PRb/PRb/PRc/PRh/PSD+vSr+fTG+PTY+PTi9/To9/Tt9/Tw9/Ty" +
            "9/Tz/PVr/PVr/PVr/PVr/PVs/PVs/PVt/PWB+vWm+fXE+PXW9/Xh9/Xo9/Xt9/Xw9/Xy9vXz/PZ6/PZ6/PZ6/PZ6/PZ6/PZ7/PZ7" +
            "/PaD+/ah+fbB+PbV9/bg9/bo9/bs9/bw9/bx9/bz/wAa/wAa/wAa/wAa/wAs/wBV/wCA/wCk/wDB/wDV/wDj/wDs/wDy/wD3/wD5" +
            "/wD7/wD9/wAZ/wAZ/wAZ/wAZ/wAs/wBU/wB//wCk/wDB/wDV/wDj/wDs/wDy/wD3/wD5/wD7/wD9/wAX/wAX/wAX/wAY/wAq/wBU" +
            "/wB//wCk/wDA/wDV/wDj/wDs/wDy/wD2/wD5/wD8/wD9/yQS/yUS/ycS/ykS/ysm/ytR/yl+/yOj/xzA/xXU/wvj/wTs/wHy/wD2" +
            "/wD5/wD7/wD9/2EI/2EI/2II/2MI/2Qd/2VN/2R7/2Oh/2C+/1rT/1Lh/0Tr/zDx/xX2/wj5/wD7/wD9/4wC/4wC/4wC/40C/44O" +
            "/45H/454/46f/428/4vR/4fg/4Hp/3bv/2n0/1L4/z36/yz8/60A/60A/60A/64A/68A/68//690/6+c/6+6/67Q/6ze/6rn/6Xt" +
            "/5/y/5b1/4r4/3z6/8UA/8UA/8UA/8UA/8YA/8Y2/8Zw/8ea/8e5/8bO/8bc/8Xm/8Ps/8Dw/7z0/7f2/7H4/9UB/9UB/9YB/9YB" +
            "/9YB/9Yt/9dr/9eY/9a3/9bN/9bb/9bl/9Xr/9Tv/9Ly/9D0/872/+AH/+EH/+EH/+EH/+EI/+Em/+Fm/+GV/+G1/+HM/uHa/uHk" +
            "/uHq/uDu/+Dx/9/z/971/+gW/+gX/+gW/+gX/+gX/+gn/+hh/+iS/ui0/ejL/Oja++jj++jp++ju++jx/Ofz/Of0/+0r/+0r/+0r" +
            "/+0r/+0s/+0w/+1b/u2P/O2y++3K+u3Z+u3j+u3p+e3t+e3w+uzy+uz0/vA///A///A//vBA//BA//BC/vBZ/fCK/PCw+/DJ+vDZ" +
            "+fDi+fDp+PDt+PDw+PDy+fD0/vNQ/vNQ/vNQ/vJQ/vNR/vNR/vNb/fOF+/Kt+vLI+fLY+fLi+PLo+PLt+PLw+PLy+PLz/fRh/fRh" +
            "/fRh/fRh/fRi/fRi/fRl/PSB+/So+vTF+fTX+PTi+PTo+PTt9/Tw9/Ty9/Tz/fVw/fVw/fVx/fVx/fVx/fVx/fVy/PWB+/Wk+vXD" +
            "+fXW+PXh+PXo+PXs9/Xw9/Xy9/Xz/PZ+/PZ//PZ//PZ//PZ//PZ//PaA/PaG+/ah+va/+fbU+Pbg+Pbn+Pbs9/bv9/by9/bz/wAg" +
            "/wAg/wAg/wAh/wAo/wBP/wB8/wCi/wC//wDU/wDj/wDs/wDy/wD2/wD5/wD7/wD9/wAg/wAg/wAg/wAg/wAn/wBP/wB8/wCi/wC/" +
            "/wDU/wDj/wDs/wDy/wD2/wD5/wD7/wD9/wAe/wAe/wAe/wAf/wAl/wBN/wB7/wCh/wC//wDU/wDj/wDs/wDy/wD2/wD5/wD7/wD9" +
            "/zIa/zMa/zQa/zYa/zgh/zlL/zd5/zOg/y6+/yTT/xXi/wjs/wPy/wD2/wD5/wD7/wD9/2gS/2kS/2kS/2oS/2sZ/2xG/2x3/2ue" +
            "/2m9/2TS/13g/1Lq/0Dx/yn2/xX5/wD7/wD9/5EG/5EG/5IG/5IG/5ML/5Q+/5Rz/5Sc/5O7/5HQ/47f/4np/3/v/3T0/1/3/0z6" +
            "/zf8/7EA/7EA/7EA/7IA/7IA/7M1/7Nv/7OZ/7K5/7LO/7Dd/67n/6rt/6Xy/531/5L4/4P6/8cA/8cA/8gA/8gA/8gA/8gs/8lq" +
            "/8mX/8m3/8nN/8jc/8fl/8Xr/8Pw/7/z/7v2/7X3/9cD/9cD/9cD/9cE/9cE/9gm/9hl/9iU/9i1/9jM/9jb/9fk/9fq/9bv/9Ty" +
            "/9L0/9D2/+IS/+ES/+ES/+IT/+IT/+Ik/+Jg/+KR/+K0/+LL/+La/+Lj/+Lq/+Hu/+Hx/+Dz/9/1/+kk/+kk/+kk/+kk/+kk/+kr" +
            "/+lb/+mO/+my/unK/enZ/Onj/Onp/Onu/Ojx/Ojz/ej0/+01/+01/+01/+01/+02/+04/+1Y/+2L/e2w/O3J++3Z++3i+u3p+u3t" +
            "+u3w+u3y+u30//BH//BH//BI//BI//FI//FJ//FY/vCF/fCu+/DI+vDY+vDi+fDo+fDt+fDw+fDy+fD0/vNX/vNX/vNX/vNX/vNY" +
            "/vNY/vNc/fOB/POr+/PG+vLX+fLi+fLo+fLt+PLw+PLy+PLz/vRn/vRn/vRn/vRn/vRo/vRo/vRq/fR//PSm+/TE+vTW+fTh+fTo" +
            "+PTs+PTw+PTy+PTz/fV2/fV2/fV2/fV2/fV2/fV3/fV3/fWC/PWi+vXB+vXV+fXh+PXo+PXs+PXv+PXy+PXz/faD/faD/faD/faE" +
            "/faE/faE/faF/faI/Pag+/a++vbU+fbg+Pbn+Pbs+Pbv+Pby+Pbz";
        internal const uint GRADE_LUT_FNV = 0xfad306d7u;
        internal const string GRADE_BAKED_FROM =
            "break=0;vol=Post_Main,global=1,weight=1,priority=0;gradingMode=HighDefinitionRange;externalLut=-;ton" +
            "emapper=ACES;toneCurveToeStrength=-;toneCurveToeLength=-;toneCurveShoulderStrength=-;toneCurveShould" +
            "erLength=-;toneCurveShoulderAngle=-;toneCurveGamma=-;ldrLut=-;ldrLutContribution=-;temperature=-;tin" +
            "t=-;colorFilter=-;hueShift=-;saturation=15;brightness=-;postExposure=1.5;contrast=45;mixerRedOutRedI" +
            "n=100;mixerRedOutGreenIn=0;mixerRedOutBlueIn=0;mixerGreenOutRedIn=-;mixerGreenOutGreenIn=-;mixerGree" +
            "nOutBlueIn=-;mixerBlueOutRedIn=-;mixerBlueOutGreenIn=-;mixerBlueOutBlueIn=-;lift=0.8398813,0.9223522" +
            ",1,0;gamma=0.884216,0.913161933,1,0;gain=1,0.643631637,0.30867672,0;masterCurve=-;redCurve=-;greenCu" +
            "rve=-;blueCurve=-;hueVsHueCurve=-;hueVsSatCurve=-;satVsSatCurve=-;lumVsSatCurve=-;enabled=1;";

        private const int LUT_N = 17;
        internal const int LUT_BYTES = LUT_N * LUT_N * LUT_N * 3;   // 14,739

        private static byte[] _gradeLut;
        private static bool _gradeBaked;
        private static string _gradeState = "";

        /// <summary>The baked marker's text, assembled at run time so the
        /// literal SCR_GRADE_TABLE=BAKED is in a build only when a bake's
        /// GRADE_TABLE_MARKER constant is.</summary>
        private static string MarkerBaked() { return string.Concat("SCR_GRADE_TABLE", "=", "BAKED"); }

        /// <summary>The digest GRADE_LUT_FNV holds: FNV-1a over the table bytes
        /// and then the UTF-8 bytes of the baked-from key, so a table and a key
        /// from two different bakes do not pass together.</summary>
        internal static uint GradeDigest(byte[] table, string key)
        {
            return Fnv32(Encoding.UTF8.GetBytes(key ?? ""), Fnv32(table));
        }

        /// <summary>Decodes the compiled table once. It is used only when it is
        /// LUT_BYTES long, its digest with GRADE_BAKED_FROM is GRADE_LUT_FNV,
        /// the key is not empty, the digest is the one RECIPE_GRADE_FNV names,
        /// and GRADE_TABLE_MARKER is the baked marker. Anything else leaves the
        /// identity placeholder in place with GradeBaked false. Logs its state
        /// once, with the marker.</summary>
        private static void LoadGrade()
        {
            if (_gradeLut != null) return;
            byte[] t = null;
            string why;
            if (GRADE_LUT_B64.Length == 0) why = "placeholder";
            else
            {
                try
                {
                    t = Convert.FromBase64String(GRADE_LUT_B64);
                    if (t.Length != LUT_BYTES) { why = "invalid: " + t.Length + " bytes"; t = null; }
                    else
                    {
                        uint h = GradeDigest(t, GRADE_BAKED_FROM);
                        if (h != GRADE_LUT_FNV) { why = "invalid: digest " + h.ToString("x8") + " != " + GRADE_LUT_FNV.ToString("x8"); t = null; }
                        else if (GRADE_BAKED_FROM.Length == 0) { why = "invalid: no baked-from key"; t = null; }
                        else if (h != RECIPE_GRADE_FNV) { why = "invalid: table " + h.ToString("x8") + " is not the one RECIPE " + RECIPE + " names (" + RECIPE_GRADE_FNV.ToString("x8") + ")"; t = null; }
                        else if (GRADE_TABLE_MARKER != MarkerBaked()) { why = "invalid: the marker still says placeholder"; t = null; }
                        else why = "baked fnv=" + h.ToString("x8");
                    }
                }
                catch (Exception ex) { why = "invalid: " + ex.Message; t = null; }
            }
            _gradeBaked = t != null;
            _gradeLut = t ?? IdentityTable();
            _gradeState = why;
            try
            {
                string line = "[PORTRAIT-GRADE] " + GRADE_TABLE_MARKER + " table " + why + " recipe=" + RECIPE;
                if (!_gradeBaked && GRADE_LUT_B64.Length > 0) Plugin.Log.LogWarning(line);
                else Plugin.Log.LogInfo(line);
            }
            catch { }
        }

        /// <summary>True only when the compiled table is a real bake.</summary>
        internal static bool GradeBaked { get { LoadGrade(); return _gradeBaked; } }
        /// <summary>The table the product path grades with: the bake, or the identity placeholder.</summary>
        private static byte[] GradeTable { get { LoadGrade(); return _gradeLut; } }
        private static string GradeTag() { LoadGrade(); return _gradeState; }

        private static int NodeValue(int k) { return k >= LUT_N - 1 ? 255 : k * 16; }

        // Per input byte: the lower node index and the upper node's weight in
        // 1/256ths. Below 240 a cell is 16 levels wide (exact); the last cell,
        // 240..255, is 15 wide and its weight is rounded to the nearest 1/256.
        private static readonly byte[] s_lutLo = BuildLutLo();
        private static readonly short[] s_lutW = BuildLutW();

        private static byte[] BuildLutLo()
        {
            var a = new byte[256];
            for (int c = 0; c < 256; c++) a[c] = (byte)(c < 240 ? c >> 4 : 15);
            return a;
        }

        private static short[] BuildLutW()
        {
            var a = new short[256];
            for (int c = 0; c < 256; c++) a[c] = (short)(c < 240 ? (c & 15) * 16 : ((c - 240) * 256 + 7) / 15);
            return a;
        }

        /// <summary>The table that maps every colour to itself. Through it each
        /// output channel of LutSample depends only on its own input, and all
        /// 256 levels come back unchanged with the node spacing and rounding
        /// above -- so grading with the placeholder is an exact no-op.</summary>
        private static byte[] IdentityTable()
        {
            var t = new byte[LUT_BYTES];
            for (int ri = 0; ri < LUT_N; ri++)
                for (int gi = 0; gi < LUT_N; gi++)
                    for (int bi = 0; bi < LUT_N; bi++)
                    {
                        int o = ((ri * LUT_N + gi) * LUT_N + bi) * 3;
                        t[o] = (byte)NodeValue(ri); t[o + 1] = (byte)NodeValue(gi); t[o + 2] = (byte)NodeValue(bi);
                    }
            return t;
        }

        /// <summary>Grades straight colour in place through `lut`: every pixel
        /// with a > 0 gets its RGB replaced by the trilinear table value; alpha
        /// is never written and a == 0 pixels are not touched. Throws on a
        /// table of the wrong size, so a bad table fails the render instead of
        /// passing ungraded pixels.
        ///
        /// Kept as sample-then-write so a strength blend between the input and
        /// the sampled colour could sit between the two; there is none.</summary>
        internal static void GradePixels(Color32[] px, byte[] lut)
        {
            if (px == null) return;
            if (lut == null || lut.Length != LUT_BYTES) throw new ArgumentException("grade table must be " + LUT_BYTES + " bytes");
            for (int i = 0; i < px.Length; i++)
            {
                if (px[i].a == 0) continue;
                byte r, g, b;
                LutSample(lut, px[i].r, px[i].g, px[i].b, out r, out g, out b);
                px[i].r = r; px[i].g = g; px[i].b = b;
            }
        }

        /// <summary>Integer trilinear lookup: lerp along blue, then green, then
        /// red, in 1/256 weights, rounded once at the end. No floating point, so
        /// the result is the same on every machine.</summary>
        internal static void LutSample(byte[] lut, int r, int g, int b, out byte ro, out byte go, out byte bo)
        {
            int o = ((s_lutLo[r] * LUT_N + s_lutLo[g]) * LUT_N + s_lutLo[b]) * 3;
            int wr = s_lutW[r], wg = s_lutW[g], wb = s_lutW[b];
            ro = Tri(lut, o, wr, wg, wb);
            go = Tri(lut, o + 1, wr, wg, wb);
            bo = Tri(lut, o + 2, wr, wg, wb);
        }

        private static byte Tri(byte[] lut, int i, int wr, int wg, int wb)
        {
            const int dB = 3, dG = LUT_N * 3, dR = LUT_N * LUT_N * 3;
            // the lower node index is at most 15, so every +1 corner exists
            int c00 = lut[i] * (256 - wb) + lut[i + dB] * wb;                        // <= 65,280
            int c01 = lut[i + dG] * (256 - wb) + lut[i + dG + dB] * wb;
            int c10 = lut[i + dR] * (256 - wb) + lut[i + dR + dB] * wb;
            int c11 = lut[i + dR + dG] * (256 - wb) + lut[i + dR + dG + dB] * wb;
            int c0 = c00 * (256 - wg) + c01 * wg;                                      // <= 16,711,680
            int c1 = c10 * (256 - wg) + c11 * wg;
            long v = (long)c0 * (256 - wr) + (long)c1 * wr;                            // <= 255 * 2^24
            return (byte)((v + (1L << 23)) >> 24);
        }

        /// <summary>FNV-1a 32; `h` continues a digest already begun.</summary>
        private static uint Fnv32(byte[] d, uint h = 2166136261u)
        {
            for (int i = 0; i < d.Length; i++) { h ^= d[i]; h *= 16777619u; }
            return h;
        }

        // ── the live grade: what MainCamera renders players with ──────────────

        private sealed class GradeSource
        {
            internal PostProcessLayer layer;
            internal string how = "none";
            internal readonly List<PostProcessVolume> volumes = new List<PostProcessVolume>();
            internal readonly List<ColorGrading> grades = new List<ColorGrading>();
            internal string key;       // canonical text of every grading input; null when unreadable
            internal string problem;   // why a bake cannot reproduce it; null when it can
        }

        private static PostProcessLayer MainPostLayer(out string how)
        {
            how = "none";
            try
            {
                var mc = MainCam.instance;
                if (mc != null && mc.cam != null)
                {
                    var l = mc.cam.GetComponent<PostProcessLayer>();
                    if (l != null) { how = "MainCam.instance '" + mc.cam.name + "'"; return l; }
                }
            }
            catch { }
            try
            {
                foreach (var l in UnityEngine.Object.FindObjectsOfType<PostProcessLayer>())
                    if (l != null && l.gameObject.name == "MainCamera") { how = "by name"; return l; }
            }
            catch { }
            return null;
        }

        /// <summary>Reads the volumes whose ColorGrading reaches MainCamera's
        /// layer, in the manager's blend order, straight from the profile each
        /// volume renders (#263: the instantiated profile when there is one).
        /// The key names each such volume and every grading parameter: '-' for
        /// one the volume does not override, its value otherwise.
        ///
        /// Volumes, not the layer's blended bundle: blending interpolates a
        /// curve's cached samples and leaves the bundle's curve at its default,
        /// so a bundle copy would lose a volume's curves.</summary>
        private static GradeSource ReadGradeSource()
        {
            var src = new GradeSource();
            try
            {
                src.layer = MainPostLayer(out src.how);
                if (src.layer == null) { src.problem = "no PostProcessLayer on MainCamera"; return src; }
                var vols = new List<PostProcessVolume>();
                PostProcessManager.instance.GetActiveVolumes(src.layer, vols, true, true);
                var sb = new StringBuilder();
                sb.Append("break=").Append(src.layer.breakBeforeColorGrading ? 1 : 0).Append(';');
                foreach (var v in vols)
                {
                    if (v == null) continue;
                    var prof = v.HasInstantiatedProfile() ? v.profile : v.sharedProfile;
                    ColorGrading cg;
                    if (prof == null || !prof.TryGetSettings(out cg) || cg == null) continue;
                    if (!cg.active || !cg.enabled.value) continue;   // PostProcessLayer.OverrideSettings skips these
                    src.volumes.Add(v); src.grades.Add(cg);
                    sb.Append("vol=").Append(Clean(v.gameObject.name)).Append(",global=").Append(v.isGlobal ? 1 : 0)
                      .Append(",weight=").Append(F(v.weight)).Append(",priority=").Append(F(v.priority)).Append(';');
                    AppendParams(sb, cg);
                }
                src.key = sb.ToString();
                if (src.grades.Count == 0) src.problem = "no active colour grading reaches MainCamera";
                else if (src.grades.Count > 1) src.problem = src.grades.Count + " colour grading volumes reach MainCamera; the bake reproduces exactly one";
                else if (!src.volumes[0].isGlobal) src.problem = "the grading volume is not global";
            }
            catch (Exception ex) { src.problem = "read threw: " + ex.Message; }
            return src;
        }

        private static void AppendParams(StringBuilder sb, PostProcessEffectSettings s)
        {
            var fields = s.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public);
            Array.Sort(fields, (a, b) => a.MetadataToken.CompareTo(b.MetadataToken));
            foreach (var f in fields)
            {
                if (!typeof(ParameterOverride).IsAssignableFrom(f.FieldType)) continue;
                var p = f.GetValue(s) as ParameterOverride;
                sb.Append(f.Name).Append('=');
                if (p == null) sb.Append("null");
                else if (!p.overrideState) sb.Append('-');
                else
                {
                    var vf = p.GetType().GetField("value", BindingFlags.Instance | BindingFlags.Public);
                    sb.Append(vf == null ? "?" : Fmt(vf.GetValue(p)));
                }
                sb.Append(';');
            }
        }

        private static string F(float x) { return x.ToString("R", CultureInfo.InvariantCulture); }

        private static string Fmt(object v)
        {
            if (v == null) return "null";
            if (v is float) return F((float)v);
            if (v is bool) return (bool)v ? "1" : "0";
            if (v is Color) { var c = (Color)v; return F(c.r) + "," + F(c.g) + "," + F(c.b) + "," + F(c.a); }
            if (v is Vector4) { var q = (Vector4)v; return F(q.x) + "," + F(q.y) + "," + F(q.z) + "," + F(q.w); }
            if (v is Vector3) { var q = (Vector3)v; return F(q.x) + "," + F(q.y) + "," + F(q.z); }
            if (v is Vector2) { var q = (Vector2)v; return F(q.x) + "," + F(q.y); }
            if (v is Spline) return FmtSpline((Spline)v);
            var uo = v as UnityEngine.Object;
            if (uo != null) return Clean(uo.name);
            if (v is UnityEngine.Object) return "null";   // destroyed
            return Clean(Convert.ToString(v, CultureInfo.InvariantCulture));
        }

        private static string FmtSpline(Spline s)
        {
            var sb = new StringBuilder();
            foreach (var n in new[] { "m_Loop", "m_ZeroValue", "m_Range" })
            {
                var f = typeof(Spline).GetField(n, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                sb.Append(f == null ? "?" : Fmt(f.GetValue(s))).Append(',');
            }
            if (s.curve == null) sb.Append("nocurve");
            else
                foreach (var k in s.curve.keys)
                    sb.Append(F(k.time)).Append(':').Append(F(k.value)).Append(':').Append(F(k.inTangent)).Append(':').Append(F(k.outTangent)).Append(' ');
            return sb.ToString().Trim();
        }

        /// <summary>Key-safe text: no field or value separators, no quotes or
        /// backslashes (the key is pasted into source as a string literal).</summary>
        private static string Clean(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length);
            foreach (var ch in s) sb.Append(ch == ';' || ch == '=' || ch == '"' || ch == '\\' || ch < ' ' ? '_' : ch);
            return sb.ToString();
        }

        /// <summary>The render-time probe (a log line, never a refusal): does
        /// the grade MainCamera renders with now match the one the compiled
        /// table was baked from? A game update that changes Post_Main moves the
        /// `g=` tag and re-renders every portrait, but with this same table.</summary>
        private static string GradeProbeLine()
        {
            var src = ReadGradeSource();
            string live = src.key == null ? "unavailable (" + src.problem + ")" : "fnv=" + Fnv32(Encoding.UTF8.GetBytes(src.key)).ToString("x8");
            if (!GradeBaked) return "[PORTRAIT-GRADE] table " + GradeTag() + "; live grade " + live;
            if (src.key == null) return "[PORTRAIT-GRADE] live grade " + live + "; table " + GradeTag();
            if (src.key == GRADE_BAKED_FROM) return "[PORTRAIT-GRADE] live grade matches the bake (" + live + ")";
            return "[PORTRAIT-GRADE] MISMATCH: the live grade differs from the bake in " + KeyDiff(GRADE_BAKED_FROM, src.key)
                 + " (live " + live + ", baked fnv=" + Fnv32(Encoding.UTF8.GetBytes(GRADE_BAKED_FROM)).ToString("x8") + ")";
        }

        private static void LogGradeProbe()
        {
            try
            {
                string line = GradeProbeLine();
                if (line.IndexOf("MISMATCH", StringComparison.Ordinal) >= 0) Plugin.Log.LogWarning(line);
                else Plugin.Log.LogInfo(line);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[PORTRAIT-GRADE] probe threw: " + ex.Message); }
        }

        private static string KeyDiff(string baked, string live)
        {
            var a = baked.Split(';'); var b = live.Split(';');
            if (a.Length != b.Length) return "structure (" + a.Length + " vs " + b.Length + " fields)";
            var sb = new StringBuilder();
            for (int i = 0; i < a.Length && sb.Length < 700; i++)
            {
                if (a[i] == b[i]) continue;
                if (sb.Length > 0) sb.Append(", ");
                sb.Append(Trunc(a[i], 80)).Append(" -> ").Append(Trunc(b[i], 80));
            }
            return sb.ToString();
        }

        // ── dev levers: the bake, the calibration swatches, the light probe ───

        private static readonly List<UnityEngine.Object> _gradeObjs = new List<UnityEngine.Object>();

        private static T Own<T>(T o) where T : UnityEngine.Object { if (o != null) _gradeObjs.Add(o); return o; }

        /// <summary>Destroys every object a grade lever made (newest first).
        /// Called from the levers' own finally and from ForceAbort (Reclaim, the
        /// coroutine host's destruction, a scene unload), which covers a lever
        /// coroutine that never unwound. Never from Teardown: a render's cleanup
        /// has no business with a lever's objects.</summary>
        private static void DestroyGradeObjects()
        {
            for (int i = _gradeObjs.Count - 1; i >= 0; i--)
            {
                var o = _gradeObjs[i];
                try
                {
                    if (o == null) continue;
                    var go = o as GameObject;
                    if (go != null) { var cam = go.GetComponent<Camera>(); if (cam != null) cam.targetTexture = null; }
                    var rt = o as RenderTexture;
                    if (rt != null) rt.Release();
                    UnityEngine.Object.Destroy(o);
                }
                catch { }
            }
            _gradeObjs.Clear();
        }

        /// <summary>A grade lever output name, with _ungraded before the
        /// extension for the negative control.</summary>
        private static string GradeOutput(string name, bool control)
        {
            if (!control) return name;
            int dot = name.LastIndexOf('.');
            return dot < 0 ? name + "_ungraded" : name.Substring(0, dot) + "_ungraded" + name.Substring(dot);
        }

        private static readonly Vector3 GRADE_PARK = new Vector3(-4000f, 4000f, 0f);
        private const int CHART_CELL = 8;        // px per node cell; the readback averages the central 4x4
        private const int CHART_TILES_X = 5;     // 17 blue slices of 17x17 cells: 5 across, 4 down
        private const int CHART_W = CHART_TILES_X * LUT_N * CHART_CELL;   // 680
        private const int CHART_H = 4 * LUT_N * CHART_CELL;               // 544
        private const int RAW_MAX_ERR = 1;       // the ungraded chart must read back as authored
        private const int CELL_MAX_SPREAD = 6;   // a graded cell must be flat (dither only)
        private const int GRADE_MIN_MEAN_DELTA = 8;   // the graded chart must actually differ from the raw one
        private const int SWATCH_TOLERANCE = 6;  // verification plan step 2

        // verification plan step 2: the authored swatches checked against MainCamera
        private static readonly int[][] SWATCHES =
        {
            new[] { 164, 74, 44 }, new[] { 43, 80, 149 }, new[] { 184, 61, 186 }, new[] { 204, 204, 204 }, new[] { 38, 38, 38 }
        };

        private static void ChartCell(int ri, int gi, int bi, out int cx, out int cy)
        {
            cx = (bi % CHART_TILES_X) * LUT_N + ri;
            cy = (bi / CHART_TILES_X) * LUT_N + gi;
        }

        /// <summary>`portrait:gradebake`: renders a 17^3 chart of exact sRGB
        /// bytes twice in the same frames -- through a bare camera, and through a
        /// camera whose PostProcessLayer sees ONLY a private global volume holding
        /// a copy of the colour grading that reaches MainCamera -- and writes the
        /// graded cell values as the table.
        ///
        /// Harness choices: the chart is an sRGB, point-filtered, clamped texture
        /// on an unlit Sprites/Default sprite mapped 1:1 to the render texture.
        /// Both targets are default-format (8-bit) render textures without MSAA,
        /// read back as RGBA32 as Grab reads the portrait; the portrait's own
        /// target differs (4x MSAA, allowHDR off). Because the bake camera has a
        /// target texture, PPv2 takes its working format from that texture
        /// (PostProcessLayer.BuildCommandBuffers), so the grade reads an 8-bit
        /// copy of the chart whatever allowHDR says, where MainCamera, which has
        /// no target texture, grades a half-float copy. That copy is lossless for
        /// the chart's nodes, which are exact sRGB bytes; an input above 1.0 is
        /// not represented in the table at all. The bake camera has no
        /// anti-aliasing and its volume carries no bloom, vignette or aberration;
        /// each cell is read as the mean of its central 4x4 pixels (the final
        /// pass dithers).
        ///
        /// The table files are written only when: the bare chart reads back
        /// within RAW_MAX_ERR of every authored byte (the sRGB round trip, the
        /// orientation and the cell mapping are right for the bare camera), every
        /// graded cell is flat within CELL_MAX_SPREAD, the graded chart differs
        /// from the bare one by at least GRADE_MIN_MEAN_DELTA on average (the
        /// grade ran), and the graded readback passes GradedRegistration (its
        /// cells are where the bare chart's are). A real bake deletes the
        /// previous bake's table files before it renders anything, so a refused
        /// bake leaves none.
        ///
        /// An option this lever does not know refuses it before anything is
        /// deleted or rendered (report pc_grade_report_refused.txt). `ungraded`
        /// is the negative control: nothing is deleted, no table is ever
        /// written, its report and charts carry the _ungraded suffix, and its
        /// outcome is NEGATIVE CONTROL PASSED only when the grade-ran check
        /// refused it (INCONCLUSIVE for any other ending, FAILED if every check
        /// passed). Both grade levers are refused by DevRun, and end after any
        /// yield, whenever DevLeverBlocked refuses (a room, a spectate, a game
        /// in this scene, or the lever's claim gone).
        ///
        /// Output in BepInEx/: pc_grade_chart_raw.png, pc_grade_chart_graded.png,
        /// pc_grade_report.txt and, on success, pc_grade_lut.bin and
        /// pc_grade_lut.cs.txt (the four constants, ready to paste).</summary>
        private static IEnumerator GradeBakeRun(string spec, int gen)
        {
            var rep = new StringBuilder();
            float t0 = Time.realtimeSinceStartup;
            _cleanupOwed = true;
            string outcome = "aborted";
            // Options are read before anything is touched: an unrecognised one
            // refuses the whole lever, so a mistyped control never runs a real
            // bake. The control writes only *_ungraded files (see GradeOutput).
            bool ungraded = false;
            string unknown = null;
            var bakeParts = spec.Split(',');
            for (int i = 1; i < bakeParts.Length; i++)
            {
                var p = bakeParts[i].Trim().ToLowerInvariant();
                if (p.Length == 0) continue;
                if (p == "ungraded") ungraded = true;   // negative control: the graded camera gets no PostProcessLayer; the bake must refuse on the grade-ran check
                else unknown = unknown == null ? p : unknown + "," + p;
            }
            string reportName = unknown != null ? "pc_grade_report_refused.txt" : GradeOutput("pc_grade_report.txt", ungraded);
            try
            {
                rep.Append("grade bake ").Append(DateTime.UtcNow.ToString("u")).Append(" spec=").Append(spec)
                   .Append(" colorSpace=").Append(QualitySettings.activeColorSpace).Append(" recipe=").Append(RECIPE)
                   .Append(ungraded ? " NEGATIVE CONTROL" : "").Append('\n');
                if (unknown != null) { outcome = "refused: unknown option(s) " + unknown + " (nothing deleted, nothing baked)"; yield break; }
                if (!ungraded)
                {
                    // A table file on disk is always this bake's: a refused bake must not
                    // leave the previous bake's files for `grade=file` or a paste to use.
                    // The control writes no table, so it leaves them.
                    foreach (var stale in new[] { "pc_grade_lut.bin", "pc_grade_lut.cs.txt" })
                    {
                        string sp = Path.Combine(BepInEx.Paths.BepInExRootPath, stale);
                        string delErr = null;
                        try { if (File.Exists(sp)) { File.Delete(sp); rep.Append("deleted the previous ").Append(stale).Append('\n'); } }
                        catch (Exception ex) { delErr = ex.Message; }
                        if (delErr != null) { outcome = "refused: could not delete the previous " + stale + ": " + delErr; yield break; }
                    }
                }
                yield return new WaitForEndOfFrame();
                _renderClaim.Beat(gen, DEV_BUDGET);
                string blocked = DevLeverBlocked(gen);
                if (blocked != null) { outcome = "aborted: " + blocked; yield break; }

                if (_layer < 0) _layer = CardSnapshot.PickIsolationLayer();
                rep.Append("isolation layer ").Append(_layer).Append('\n');
                var src = ReadGradeSource();
                rep.Append("main layer: ").Append(src.how).Append('\n');
                rep.Append("live key: ").Append(src.key ?? "null").Append('\n');
                if (src.problem != null) { outcome = "refused: " + src.problem; yield break; }

                Camera graded, raw; RenderTexture rtG, rtR;
                string err = SetupBake(src, rep, ungraded, out graded, out raw, out rtG, out rtR);
                if (err != null) { outcome = "refused: " + err; yield break; }

                for (int i = 0; i < 4; i++)   // volume blending and the grading tables settle
                {
                    yield return null;
                    _renderClaim.Beat(gen, DEV_BUDGET);
                    if ((blocked = DevLeverBlocked(gen)) != null) { outcome = "aborted: " + blocked; yield break; }
                }
                yield return new WaitForEndOfFrame();
                _renderClaim.Beat(gen, DEV_BUDGET);
                if ((blocked = DevLeverBlocked(gen)) != null) { outcome = "aborted: " + blocked; yield break; }

                outcome = FinishBake(src, rtG, rtR, rep, ungraded);
            }
            finally
            {
                // After a force-abort a successor may hold the claim: the grade
                // objects and the owed cleanup are then its own.
                if (!_renderClaim.HeldByOther(gen))
                {
                    _cleanupOwed = false;
                    DestroyGradeObjects();
                }
                // The control passes only on the grade-ran refusal (FinishBake says
                // so); any other ending proves nothing about that check.
                if (ungraded && !outcome.StartsWith("NEGATIVE CONTROL", StringComparison.Ordinal))
                    outcome = "NEGATIVE CONTROL INCONCLUSIVE: " + outcome;
                rep.Append("outcome: ").Append(outcome).Append('\n');
                rep.Append("elapsed=").Append((Time.realtimeSinceStartup - t0).ToString("F2")).Append("s\n");
                string path = "";
                try
                {
                    path = Path.Combine(BepInEx.Paths.BepInExRootPath, reportName);
                    File.WriteAllText(path, rep.ToString());
                }
                catch (Exception ex) { Plugin.Log.LogWarning("[PORTRAIT-GRADE] report write failed: " + ex.Message); }
                Plugin.Log.LogInfo("[PORTRAIT-GRADE] bake " + outcome + " report=" + path);
                _renderClaim.Drop(gen);
            }
        }

        private static string SetupBake(GradeSource src, StringBuilder rep, bool ungraded, out Camera graded, out Camera raw, out RenderTexture rtG, out RenderTexture rtR)
        {
            graded = null; raw = null; rtG = null; rtR = null;
            try
            {
                var mainCam = src.layer.GetComponent<Camera>();
                if (mainCam == null) return "MainCamera's PostProcessLayer has no Camera";
                int bit = 1 << _layer;
                foreach (var l in UnityEngine.Object.FindObjectsOfType<PostProcessLayer>())
                    if (l != null && (l.volumeLayer.value & bit) != 0) return "PostProcessLayer on '" + l.gameObject.name + "' reads volumes on the isolation layer";
                foreach (var c in Camera.allCameras)
                    if (c != null && (c.cullingMask & bit) != 0) return "camera '" + c.name + "' renders the isolation layer";
                var res = typeof(PostProcessLayer).GetField("m_Resources", BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(src.layer) as PostProcessResources;
                if (res == null) return "MainCamera's PostProcessResources are unreadable";
                var sh = Shader.Find("Sprites/Default");
                if (sh == null) return "no Sprites/Default shader";

                // the chart: node (ri, gi, bi) authored as its exact sRGB bytes
                var chart = new Color32[CHART_W * CHART_H];
                for (int ri = 0; ri < LUT_N; ri++)
                    for (int gi = 0; gi < LUT_N; gi++)
                        for (int bi = 0; bi < LUT_N; bi++)
                        {
                            int cx, cy; ChartCell(ri, gi, bi, out cx, out cy);
                            var col = new Color32((byte)NodeValue(ri), (byte)NodeValue(gi), (byte)NodeValue(bi), 255);
                            for (int dy = 0; dy < CHART_CELL; dy++)
                                for (int dx = 0; dx < CHART_CELL; dx++)
                                    chart[(cy * CHART_CELL + dy) * CHART_W + cx * CHART_CELL + dx] = col;
                        }
                for (int i = 0; i < chart.Length; i++) if (chart[i].a == 0) chart[i] = new Color32(0, 0, 0, 255);   // the three unused tiles
                var tex = Own(new Texture2D(CHART_W, CHART_H, TextureFormat.RGBA32, false, false));   // sRGB: sampled to linear, written back to an sRGB target
                tex.filterMode = FilterMode.Point;
                tex.wrapMode = TextureWrapMode.Clamp;
                tex.SetPixels32(chart);
                tex.Apply(false, false);
                var sprite = Own(Sprite.Create(tex, new Rect(0, 0, CHART_W, CHART_H), new Vector2(0.5f, 0.5f), CHART_CELL, 0, SpriteMeshType.FullRect));

                var chartGO = Own(new GameObject("CR_GradeChart"));
                chartGO.hideFlags = HideFlags.HideAndDontSave;
                chartGO.layer = _layer;
                chartGO.transform.position = GRADE_PARK;
                var sr = chartGO.AddComponent<SpriteRenderer>();
                sr.sprite = sprite;
                sr.sharedMaterial = Own(new Material(sh));
                sr.color = Color.white;

                // the private volume: a copy of the ONE grading volume that reaches MainCamera
                var profile = Own(ScriptableObject.CreateInstance<PostProcessProfile>());
                var cg = Own(UnityEngine.Object.Instantiate(src.grades[0]));   // override states and values as authored
                profile.settings.Add(cg);
                profile.isDirty = true;
                var volGO = Own(new GameObject("CR_GradeBakeVolume"));
                volGO.hideFlags = HideFlags.HideAndDontSave;
                volGO.SetActive(false);
                volGO.layer = _layer;                                       // registration reads the layer at OnEnable
                var vol = volGO.AddComponent<PostProcessVolume>();
                vol.isGlobal = true;
                vol.priority = 1000f;
                vol.weight = src.volumes[0].weight;
                vol.sharedProfile = profile;
                volGO.SetActive(true);

                rtG = Own(new RenderTexture(CHART_W, CHART_H, 24));
                rtR = Own(new RenderTexture(CHART_W, CHART_H, 24));

                var gGO = Own(new GameObject("CR_GradeBakeCam"));
                gGO.hideFlags = HideFlags.HideAndDontSave;
                gGO.SetActive(false);
                gGO.transform.position = GRADE_PARK + new Vector3(0f, 0f, -10f);
                graded = gGO.AddComponent<Camera>();
                ChartCamera(graded, mainCam, rtG);
                if (ungraded)
                {
                    // Negative control: without a PostProcessLayer the "graded"
                    // chart is a second bare render, which FinishBake must refuse.
                    gGO.SetActive(true);
                    rep.Append("NEGATIVE CONTROL (ungraded): the graded camera carries no PostProcessLayer\n");
                }
                else
                {
                    var ppl = gGO.AddComponent<PostProcessLayer>();
                    ppl.Init(res);                                          // before OnEnable, which initialises with no resources of its own
                    ppl.volumeLayer = bit;
                    ppl.volumeTrigger = gGO.transform;
                    ppl.antialiasingMode = PostProcessLayer.Antialiasing.None;
                    ppl.stopNaNPropagation = true;
                    ppl.finalBlitToCameraTarget = false;
                    gGO.SetActive(true);
                    var onLayer = new List<PostProcessVolume>();
                    PostProcessManager.instance.GetActiveVolumes(ppl, onLayer, true, true);
                    if (onLayer.Count != 1 || onLayer[0] != vol) return "the bake camera sees " + onLayer.Count + " volumes, want only its own";
                }

                var rGO = Own(new GameObject("CR_GradeBakeRaw"));
                rGO.hideFlags = HideFlags.HideAndDontSave;
                rGO.transform.position = GRADE_PARK + new Vector3(0f, 0f, -10f);
                raw = rGO.AddComponent<Camera>();
                ChartCamera(raw, mainCam, rtR);

                rep.Append("main camera '").Append(mainCam.name).Append("' allowHDR=").Append(mainCam.allowHDR).Append(" allowMSAA=").Append(mainCam.allowMSAA)
                   .Append(" | bake target ").Append(rtG.format).Append(" sRGB=").Append(rtG.sRGB)
                   .Append(" | grading volume '").Append(src.volumes[0].gameObject.name).Append("' weight=").Append(F(src.volumes[0].weight)).Append('\n');
                return null;
            }
            catch (Exception ex) { return "setup threw: " + ex.Message; }
        }

        private static void ChartCamera(Camera cam, Camera main, RenderTexture rt)
        {
            cam.orthographic = true;
            cam.orthographicSize = CHART_H / (float)CHART_CELL * 0.5f;
            cam.aspect = CHART_W / (float)CHART_H;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = Color.black;
            cam.cullingMask = 1 << _layer;
            cam.nearClipPlane = 0.1f;
            cam.farClipPlane = 40f;
            cam.allowHDR = main.allowHDR;                                   // mirrors MainCamera's setting; PPv2 still grades an 8-bit copy here (see GradeBakeRun)
            cam.allowMSAA = false;
            cam.useOcclusionCulling = false;
            cam.depth = -100f;
            cam.targetTexture = rt;
            cam.enabled = true;                                             // renders in the normal camera loop, post stack included
        }

        private static string FinishBake(GradeSource src, RenderTexture rtG, RenderTexture rtR, StringBuilder rep, bool negativeControl)
        {
            try
            {
                var g = ReadTarget(rtG, CHART_W, CHART_H);
                var r = ReadTarget(rtR, CHART_W, CHART_H);
                TryWrite(rep, GradeOutput("pc_grade_chart_raw.png", negativeControl), EncodePngWH(r, CHART_W, CHART_H));
                TryWrite(rep, GradeOutput("pc_grade_chart_graded.png", negativeControl), EncodePngWH(g, CHART_W, CHART_H));

                var lut = new byte[LUT_BYTES];
                int rawErr = 0, spread = 0; long delta = 0;
                string rawWorst = "", spreadWorst = "";
                for (int ri = 0; ri < LUT_N; ri++)
                    for (int gi = 0; gi < LUT_N; gi++)
                        for (int bi = 0; bi < LUT_N; bi++)
                        {
                            int cx, cy; ChartCell(ri, gi, bi, out cx, out cy);
                            int rr, rg, rb, rs, gr, gg, gb, gs;
                            CellMean(r, cx, cy, out rr, out rg, out rb, out rs);
                            CellMean(g, cx, cy, out gr, out gg, out gb, out gs);
                            int want0 = NodeValue(ri), want1 = NodeValue(gi), want2 = NodeValue(bi);
                            int e = Math.Max(Math.Abs(rr - want0), Math.Max(Math.Abs(rg - want1), Math.Abs(rb - want2)));
                            if (e > rawErr) { rawErr = e; rawWorst = "node " + ri + "," + gi + "," + bi + " read " + rr + "," + rg + "," + rb; }
                            if (gs > spread) { spread = gs; spreadWorst = "node " + ri + "," + gi + "," + bi; }
                            delta += Math.Abs(gr - rr) + Math.Abs(gg - rg) + Math.Abs(gb - rb);
                            int o = ((ri * LUT_N + gi) * LUT_N + bi) * 3;
                            lut[o] = (byte)gr; lut[o + 1] = (byte)gg; lut[o + 2] = (byte)gb;
                        }
                float meanDelta = delta / (float)(LUT_N * LUT_N * LUT_N * 3);
                rep.Append("raw chart max error=").Append(rawErr).Append(rawErr > 0 ? " (" + rawWorst + ")" : "").Append('\n');
                rep.Append("graded cell max spread=").Append(spread).Append(spread > 0 ? " (" + spreadWorst + ")" : "").Append('\n');
                rep.Append("graded vs raw mean delta=").Append(meanDelta.ToString("F2")).Append(" levels\n");
                rep.Append("white -> ").Append(Node(lut, 16, 16, 16)).Append(" mid grey -> ").Append(Node(lut, 8, 8, 8)).Append(" black -> ").Append(Node(lut, 0, 0, 0)).Append('\n');
                foreach (var s in SWATCHES)
                {
                    byte pr, pg, pb; LutSample(lut, s[0], s[1], s[2], out pr, out pg, out pb);
                    rep.Append("swatch (").Append(s[0]).Append(',').Append(s[1]).Append(',').Append(s[2]).Append(") -> (")
                       .Append(pr).Append(',').Append(pg).Append(',').Append(pb).Append(")\n");
                }
                if (rawErr > RAW_MAX_ERR) return "refused: the bare chart read back " + rawErr + " levels off (" + rawWorst + ")";
                if (spread > CELL_MAX_SPREAD) return "refused: a graded cell is not flat, spread " + spread + " (" + spreadWorst + ")";
                if (meanDelta < GRADE_MIN_MEAN_DELTA)
                {
                    string why = "the graded chart is within " + meanDelta.ToString("F2") + " levels of the bare one; the grade did not run";
                    return negativeControl ? "NEGATIVE CONTROL PASSED (refused by the grade-ran check: " + why + ")" : "refused: " + why;
                }
                string reg = GradedRegistration(lut, rep);
                if (reg != null) return "refused: the graded readback is not registered with the chart: " + reg;

                // the live grade must still be the one copied at setup
                var again = ReadGradeSource();
                if (again.key != src.key) return "refused: the live grade changed during the bake";
                if (src.key.IndexOf('"') >= 0 || src.key.IndexOf('\\') >= 0) return "refused: the live key cannot be written as a plain string literal";
                if (negativeControl) return "NEGATIVE CONTROL FAILED: an ungraded bake passed every check (no table written)";   // before any table write: the control never writes one

                bool wrote = TryWrite(rep, "pc_grade_lut.bin", lut);
                wrote &= TryWrite(rep, "pc_grade_lut.cs.txt", Encoding.UTF8.GetBytes(CsLiteral(lut, src.key)));
                if (!wrote) return "failed: a table file could not be written (see above)";
                return "ok digest=" + GradeDigest(lut, src.key).ToString("x8") + " (table and key)";
            }
            catch (Exception ex) { return "failed: " + ex.Message; }
        }

        private const int AXIS_TOLERANCE = 2;    // dither and rounding between neighbouring nodes
        private const int AXIS_MIN_RISE = 32;    // node 16 over node 0 along each checked axis

        /// <summary>Null when the graded readback's cells sit where the bare
        /// chart's do; otherwise why not. The bare-chart check proves the cell
        /// mapping for the bare camera only, and the graded image arrives
        /// through PPv2's blits. Exposure, contrast, lift/gamma/gain, saturation
        /// and ACES each keep a channel rising along its own axis and keep the
        /// grey axis rising in luma, so along (k,0,0), (0,k,0) and (0,0,k) the
        /// graded channel of that axis, and along (k,k,k) the graded luma, must
        /// not fall by more than AXIS_TOLERANCE from one node to the next and
        /// must rise by AXIS_MIN_RISE overall. A graded image flipped either way
        /// reads nodes along those axes whose own channel falls as k rises (a
        /// vertical flip takes green, and the grey axis's luma, down; a
        /// horizontal flip takes red down).</summary>
        private static string GradedRegistration(byte[] lut, StringBuilder rep)
        {
            var sb = new StringBuilder();
            string fail = null;
            for (int axis = 0; axis < 4; axis++)
            {
                string label = axis == 0 ? "red" : axis == 1 ? "green" : axis == 2 ? "blue" : "grey luma";
                int first = 0, prev = 0;
                sb.Append(label).Append(':');
                for (int k = 0; k < LUT_N; k++)
                {
                    int ri = axis == 0 || axis == 3 ? k : 0, gi = axis == 1 || axis == 3 ? k : 0, bi = axis == 2 || axis == 3 ? k : 0;
                    int o = ((ri * LUT_N + gi) * LUT_N + bi) * 3;
                    // luma in 1/10000 levels (Rec. 709 weights); a channel scaled to match
                    int v = axis == 3 ? lut[o] * 2126 + lut[o + 1] * 7152 + lut[o + 2] * 722 : lut[o + axis] * 10000;
                    sb.Append(' ').Append((v + 5000) / 10000);
                    if (k == 0) first = v;
                    else if (fail == null && v < prev - AXIS_TOLERANCE * 10000)
                        fail = label + " falls from " + (prev + 5000) / 10000 + " to " + (v + 5000) / 10000 + " at node " + k;
                    prev = v;
                }
                if (fail == null && prev - first < AXIS_MIN_RISE * 10000)
                    fail = label + " rises only " + (prev - first + 5000) / 10000 + " from node 0 to node 16";
                sb.Append('\n');
            }
            rep.Append("graded axes (node 0..16):\n").Append(sb);
            return fail;
        }

        private static string Node(byte[] lut, int ri, int gi, int bi)
        {
            int o = ((ri * LUT_N + gi) * LUT_N + bi) * 3;
            return "(" + lut[o] + "," + lut[o + 1] + "," + lut[o + 2] + ")";
        }

        /// <summary>Mean of the central 4x4 pixels of a chart cell, rounded,
        /// and the largest per-channel max-min inside those 16.</summary>
        private static void CellMean(Color32[] px, int cx, int cy, out int r, out int g, out int b, out int spread)
        {
            int sr = 0, sg = 0, sb = 0;
            int minR = 255, minG = 255, minB = 255, maxR = 0, maxG = 0, maxB = 0;
            int x0 = cx * CHART_CELL + CHART_CELL / 2 - 2, y0 = cy * CHART_CELL + CHART_CELL / 2 - 2;
            for (int dy = 0; dy < 4; dy++)
                for (int dx = 0; dx < 4; dx++)
                {
                    var c = px[(y0 + dy) * CHART_W + x0 + dx];
                    sr += c.r; sg += c.g; sb += c.b;
                    if (c.r < minR) minR = c.r; if (c.r > maxR) maxR = c.r;
                    if (c.g < minG) minG = c.g; if (c.g > maxG) maxG = c.g;
                    if (c.b < minB) minB = c.b; if (c.b > maxB) maxB = c.b;
                }
            r = (sr + 8) / 16; g = (sg + 8) / 16; b = (sb + 8) / 16;
            spread = Math.Max(maxR - minR, Math.Max(maxG - minG, maxB - minB));
        }

        private static Color32[] ReadTarget(RenderTexture rt, int w, int h)
        {
            var prev = RenderTexture.active;
            Texture2D tex = null;
            try
            {
                RenderTexture.active = rt;
                tex = new Texture2D(w, h, TextureFormat.RGBA32, false);    // as Grab reads the portrait
                tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
                tex.Apply();
                return tex.GetPixels32();
            }
            finally
            {
                RenderTexture.active = prev;
                if (tex != null) UnityEngine.Object.Destroy(tex);
            }
        }

        private static byte[] EncodePngWH(Color32[] px, int w, int h)
        {
            Texture2D t = null;
            try
            {
                t = new Texture2D(w, h, TextureFormat.RGBA32, false);
                t.SetPixels32(px); t.Apply();
                return t.EncodeToPNG();
            }
            finally { if (t != null) UnityEngine.Object.Destroy(t); }
        }

        private static bool TryWrite(StringBuilder rep, string name, byte[] bytes)
        {
            try
            {
                string path = Path.Combine(BepInEx.Paths.BepInExRootPath, name);
                File.WriteAllBytes(path, bytes);
                rep.Append("wrote ").Append(name).Append(" bytes=").Append(bytes.Length).Append('\n');
                return true;
            }
            catch (Exception ex) { rep.Append("write ").Append(name).Append(" threw: ").Append(ex.Message).Append('\n'); return false; }
        }

        /// <summary>The four constants as C# source, wrapped at 100 characters,
        /// under the instructions for RECIPE_GRADE_FNV and RECIPE. Neither the
        /// base64 nor the key needs escaping: Clean keeps quotes and backslashes
        /// out of every name in the key, and FinishBake refuses a key that
        /// carries one anyway.</summary>
        private static string CsLiteral(byte[] lut, string key)
        {
            uint digest = GradeDigest(lut, key);
            bool sameAsCompiled = GradeBaked && digest == GRADE_LUT_FNV;
            var sb = new StringBuilder();
            sb.Append("        // baked ").Append(DateTime.UtcNow.ToString("u")).Append(" by portrait:gradebake on a build at RECIPE ").Append(RECIPE).Append('\n');
            if (sameAsCompiled)
                sb.Append("        // This is the table the build already carries: nothing to change.\n");
            else
            {
                sb.Append("        // Paste the four constants below over the ones in PortraitGrade.cs. Then in\n");
                sb.Append("        // PortraitRender.cs set RECIPE_GRADE_FNV = 0x").Append(digest.ToString("x8")).Append("u, and BUMP RECIPE unless\n");
                sb.Append("        // no released build has carried a baked table at the RECIPE in source. Add the\n");
                sb.Append("        // RECIPE -> digest pair to the ledger in backend/tests/test_portrait_grade_recipe.py.\n");
            }
            sb.Append("        internal const string GRADE_TABLE_MARKER = \"").Append(MarkerBaked()).Append("\";\n");
            sb.Append("        internal const string GRADE_LUT_B64 =\n");
            AppendWrapped(sb, Convert.ToBase64String(lut));
            sb.Append("        internal const uint GRADE_LUT_FNV = 0x").Append(digest.ToString("x8")).Append("u;\n");
            sb.Append("        internal const string GRADE_BAKED_FROM =\n");
            AppendWrapped(sb, key);
            return sb.ToString();
        }

        private static void AppendWrapped(StringBuilder sb, string s)
        {
            if (s.Length == 0) { sb.Append("            \"\";\n"); return; }
            int i = 0;
            while (i < s.Length)
            {
                int n = Math.Min(100, s.Length - i);
                sb.Append("            \"").Append(s, i, n).Append('"').Append(i + n < s.Length ? " +\n" : ";\n");
                i += n;
            }
        }

        /// <summary>The table a dev render or the swatch check uses:
        /// `compiled` (what the product grades with), `file` (the last bake's
        /// pc_grade_lut.bin, before it is pasted into source), `identity`, or
        /// `none`; `swaprb` swaps its red and blue outputs (negative control).
        /// Null when the chosen table cannot be had (the report says why).</summary>
        private static byte[] DevGradeTable(string which, bool swaprb, StringBuilder rep, out string name)
        {
            byte[] t;
            which = (which ?? "compiled").Trim().ToLowerInvariant();
            if (which == "none") { name = "none"; return null; }
            if (which == "identity") { t = IdentityTable(); name = "identity"; }
            else if (which == "file")
            {
                string path = Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_grade_lut.bin");
                try { t = File.ReadAllBytes(path); }
                catch (Exception ex) { name = "file unreadable"; rep.Append("grade file unreadable: ").Append(ex.Message).Append('\n'); return null; }
                if (t.Length != LUT_BYTES) { name = "file of " + t.Length + " bytes"; rep.Append("grade file is ").Append(t.Length).Append(" bytes, want ").Append(LUT_BYTES).Append('\n'); return null; }
                name = "file table-only-fnv=" + Fnv32(t).ToString("x8");   // the .bin holds no key, so this is not the pasted digest
            }
            else
            {
                if (which != "compiled") rep.Append("unknown grade option '").Append(which).Append("', using compiled\n");
                t = (byte[])GradeTable.Clone();
                name = "compiled " + GradeTag();
            }
            if (swaprb)
            {
                t = (byte[])t.Clone();
                for (int i = 0; i < t.Length; i += 3) { byte x = t[i]; t[i] = t[i + 2]; t[i + 2] = x; }
                name += " swaprb";
            }
            rep.Append("grade table: ").Append(name).Append('\n');
            return t;
        }

        /// <summary>`portrait:gradeswatch[,x=F][,y=F][,secs=N][,grade=compiled|file][,swaprb]`:
        /// five authored swatches, 48 px each and 96 px apart, drawn by
        /// MainCamera itself (unlit Sprites/Default on a layer it renders, top
        /// sorting layer) centred at screen fraction (x, y). After five frames
        /// the screen is read at the end of the frame; each swatch's central 5x5
        /// mean is compared with the table's prediction for its authored colour:
        /// PASS when every channel is within SWATCH_TOLERANCE. The swatches stay
        /// up `secs` seconds for an outside screenshot, then are destroyed.
        /// Output: BepInEx/pc_grade_swatch.png and pc_grade_swatch_report.txt.
        /// Bloom from the swatches and whatever the menu draws over the chosen
        /// point both reach these pixels; pick a clear spot.</summary>
        private static IEnumerator GradeSwatchRun(string spec, int gen)
        {
            var rep = new StringBuilder();
            float t0 = Time.realtimeSinceStartup;
            _cleanupOwed = true;
            string outcome = "aborted";
            float fx = 0.5f, fy = 0.5f, secs = 10f; string grade = "compiled"; bool swaprb = false;
            var parts = spec.Split(',');
            for (int i = 1; i < parts.Length; i++)
            {
                var p = parts[i].Trim().ToLowerInvariant();
                float fv;
                if (p.StartsWith("x=") && float.TryParse(p.Substring(2), NumberStyles.Float, CultureInfo.InvariantCulture, out fv)) fx = Mathf.Clamp01(fv);
                else if (p.StartsWith("y=") && float.TryParse(p.Substring(2), NumberStyles.Float, CultureInfo.InvariantCulture, out fv)) fy = Mathf.Clamp01(fv);
                else if (p.StartsWith("secs=") && float.TryParse(p.Substring(5), NumberStyles.Float, CultureInfo.InvariantCulture, out fv)) secs = Mathf.Clamp(fv, 0f, 60f);
                else if (p.StartsWith("grade=")) grade = p.Substring(6);
                else if (p == "swaprb") swaprb = true;
                else if (p.Length > 0) rep.Append("unknown option: ").Append(p).Append('\n');
            }
            try
            {
                rep.Append("grade swatch ").Append(DateTime.UtcNow.ToString("u")).Append(" spec=").Append(spec).Append('\n');
                yield return new WaitForEndOfFrame();
                _renderClaim.Beat(gen, DEV_BUDGET);
                string blocked = DevLeverBlocked(gen);
                if (blocked != null) { outcome = "aborted: " + blocked; yield break; }
                string gname;
                var table = DevGradeTable(grade, swaprb, rep, out gname);
                if (table == null) { outcome = "refused: no table (" + gname + ")"; yield break; }
                Vector2[] centres;
                string err = SpawnSwatches(fx, fy, rep, out centres);
                if (err != null) { outcome = "refused: " + err; yield break; }
                for (int i = 0; i < 5; i++)
                {
                    yield return null;
                    _renderClaim.Beat(gen, DEV_BUDGET);
                    if ((blocked = DevLeverBlocked(gen)) != null) { outcome = "aborted: " + blocked; yield break; }
                }
                yield return new WaitForEndOfFrame();
                _renderClaim.Beat(gen, DEV_BUDGET);
                if ((blocked = DevLeverBlocked(gen)) != null) { outcome = "aborted: " + blocked; yield break; }
                outcome = MeasureSwatches(centres, table, gname, rep);
                float until = Time.realtimeSinceStartup + secs;
                while (Time.realtimeSinceStartup < until)
                {
                    yield return null;
                    _renderClaim.Beat(gen, DEV_BUDGET);
                    // the squares come down (finally) at the first frame DevLeverBlocked refuses
                    if ((blocked = DevLeverBlocked(gen)) != null) { outcome += " | hold aborted: " + blocked; yield break; }
                }
            }
            finally
            {
                // After a force-abort a successor may hold the claim: the grade
                // objects and the owed cleanup are then its own.
                if (!_renderClaim.HeldByOther(gen))
                {
                    _cleanupOwed = false;
                    DestroyGradeObjects();
                }
                rep.Append("outcome: ").Append(outcome).Append('\n');
                rep.Append("elapsed=").Append((Time.realtimeSinceStartup - t0).ToString("F2")).Append("s\n");
                string path = "";
                try
                {
                    path = Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_grade_swatch_report.txt");
                    File.WriteAllText(path, rep.ToString());
                }
                catch (Exception ex) { Plugin.Log.LogWarning("[PORTRAIT-GRADE] swatch report write failed: " + ex.Message); }
                Plugin.Log.LogInfo("[PORTRAIT-GRADE] swatch " + outcome + " report=" + path);
                _renderClaim.Drop(gen);
            }
        }

        private static string SpawnSwatches(float fx, float fy, StringBuilder rep, out Vector2[] centres)
        {
            centres = new Vector2[SWATCHES.Length];
            try
            {
                string how;
                var layer = MainPostLayer(out how);
                var cam = layer != null ? layer.GetComponent<Camera>() : null;
                if (cam == null) return "no MainCamera (" + how + ")";
                var sh = Shader.Find("Sprites/Default");
                if (sh == null) return "no Sprites/Default shader";
                int goLayer = 0;
                if ((cam.cullingMask & 1) == 0)
                {
                    goLayer = -1;
                    for (int l = 0; l < 32; l++) if ((cam.cullingMask & (1 << l)) != 0) { goLayer = l; break; }
                    if (goLayer < 0) return "MainCamera renders no layer";
                }
                var sorting = SortingLayer.layers;
                int sortingId = sorting.Length > 0 ? sorting[sorting.Length - 1].id : 0;
                float dist = Mathf.Clamp(Mathf.Abs(cam.transform.position.z), cam.nearClipPlane + 0.5f, cam.farClipPlane - 0.5f);
                var mat = Own(new Material(sh));
                for (int i = 0; i < SWATCHES.Length; i++)
                {
                    float sx = fx * Screen.width + (i - SWATCHES.Length / 2) * 96f, sy = fy * Screen.height;
                    centres[i] = new Vector2(sx, sy);
                    Vector3 c = cam.ScreenToWorldPoint(new Vector3(sx, sy, dist));
                    Vector3 a = cam.ScreenToWorldPoint(new Vector3(sx - 24f, sy, dist));
                    Vector3 b = cam.ScreenToWorldPoint(new Vector3(sx + 24f, sy, dist));
                    float side = (b - a).magnitude;
                    var col = new Color32((byte)SWATCHES[i][0], (byte)SWATCHES[i][1], (byte)SWATCHES[i][2], 255);
                    var tex = Own(new Texture2D(4, 4, TextureFormat.RGBA32, false, false));   // sRGB, like the chart
                    var fill = new Color32[16];
                    for (int k = 0; k < 16; k++) fill[k] = col;
                    tex.filterMode = FilterMode.Point;
                    tex.SetPixels32(fill); tex.Apply(false, false);
                    var sprite = Own(Sprite.Create(tex, new Rect(0, 0, 4, 4), new Vector2(0.5f, 0.5f), 4f, 0, SpriteMeshType.FullRect));
                    var go = Own(new GameObject("CR_GradeSwatch" + i));
                    go.hideFlags = HideFlags.HideAndDontSave;
                    go.layer = goLayer;
                    go.transform.position = c;
                    go.transform.rotation = cam.transform.rotation;
                    go.transform.localScale = new Vector3(side, side, 1f);
                    var sr = go.AddComponent<SpriteRenderer>();
                    sr.sprite = sprite;
                    sr.sharedMaterial = mat;
                    sr.color = Color.white;
                    sr.sortingLayerID = sortingId;
                    sr.sortingOrder = 32767;
                }
                rep.Append("camera '").Append(cam.name).Append("' (").Append(how).Append(") layer=").Append(goLayer).Append(" sortingLayerId=").Append(sortingId)
                   .Append(" screen=").Append(Screen.width).Append('x').Append(Screen.height).Append('\n');
                return null;
            }
            catch (Exception ex) { return "spawn threw: " + ex.Message; }
        }

        private static string MeasureSwatches(Vector2[] centres, byte[] table, string tableName, StringBuilder rep)
        {
            Texture2D tex = null;
            try
            {
                int w = Screen.width, h = Screen.height;
                tex = new Texture2D(w, h, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
                tex.Apply();
                TryWrite(rep, "pc_grade_swatch.png", tex.EncodeToPNG());
                var px = tex.GetPixels32();
                bool all = true;
                for (int i = 0; i < SWATCHES.Length; i++)
                {
                    int cx = Mathf.Clamp(Mathf.RoundToInt(centres[i].x), 2, w - 3), cy = Mathf.Clamp(Mathf.RoundToInt(centres[i].y), 2, h - 3);
                    int sr = 0, sg = 0, sb = 0;
                    for (int dy = -2; dy <= 2; dy++)
                        for (int dx = -2; dx <= 2; dx++)
                        {
                            var c = px[(cy + dy) * w + cx + dx];
                            sr += c.r; sg += c.g; sb += c.b;
                        }
                    int mr = (sr + 12) / 25, mg = (sg + 12) / 25, mb = (sb + 12) / 25;
                    var s = SWATCHES[i];
                    byte pr, pg, pb; LutSample(table, s[0], s[1], s[2], out pr, out pg, out pb);
                    int d = Math.Max(Math.Abs(mr - pr), Math.Max(Math.Abs(mg - pg), Math.Abs(mb - pb)));
                    int du = Math.Max(Math.Abs(mr - s[0]), Math.Max(Math.Abs(mg - s[1]), Math.Abs(mb - s[2])));
                    bool pass = d <= SWATCH_TOLERANCE;
                    all &= pass;
                    rep.Append("swatch (").Append(s[0]).Append(',').Append(s[1]).Append(',').Append(s[2]).Append(") at ").Append(cx).Append(',').Append(cy)
                       .Append(" measured (").Append(mr).Append(',').Append(mg).Append(',').Append(mb).Append(") predicted (").Append(pr).Append(',').Append(pg).Append(',').Append(pb)
                       .Append(") max delta ").Append(d).Append(pass ? " PASS" : " FAIL").Append(" | ungraded delta ").Append(du).Append('\n');
                }
                return (all ? "PASS" : "FAIL") + " within " + SWATCH_TOLERANCE + " against table " + tableName;
            }
            catch (Exception ex) { return "failed: " + ex.Message; }
            finally { if (tex != null) UnityEngine.Object.Destroy(tex); }
        }

        // verification plan step 0: the SFSS lighting globals each camera renders with
        private static readonly HashSet<string> _lightProbeSeen = new HashSet<string>(StringComparer.Ordinal);
        private static bool _lightProbeOn;

        private static void StartLightProbe()
        {
            if (_lightProbeOn) return;
            _lightProbeSeen.Clear();
            Camera.onPreRender += OnLightProbe;
            _lightProbeOn = true;
        }

        private static void StopLightProbe()
        {
            if (!_lightProbeOn) return;
            Camera.onPreRender -= OnLightProbe;
            _lightProbeOn = false;
        }

        /// <summary>One line per camera name for the life of the probe.</summary>
        private static void OnLightProbe(Camera c)
        {
            try
            {
                if (c == null || _lightProbeSeen.Count >= 32 || !_lightProbeSeen.Add(c.name)) return;
                var lm = Shader.GetGlobalTexture("_SFLightMap");
                Plugin.Log.LogInfo("[PORTRAIT-LIGHT] camera '" + c.name + "' depth=" + c.depth.ToString("F0")
                                   + " _SFLightMap=" + (lm != null ? lm.name : "null")
                                   + " _SFExposure=" + Shader.GetGlobalFloat("_SFExposure").ToString("F3")
                                   + " _SFAmbientLight=" + Shader.GetGlobalColor("_SFAmbientLight"));
            }
            catch { }
        }
    }
}
