# -*- coding: utf-8 -*-
"""fe_agent/akis_atif.py - Mesajlarda adim ve faz atiflari.

"Nerede ne olacagini" soyleyen cumleler adimi is akisindaki numarasi ve
adiyla, kalin yazar: **01.2.3 Eksik Sözlük Tanımları**. Faz 01'in adim
listesi moda bagli oldugu icin numara da moda bagli; mod durumdan okunur.
On yuz ** isaretini kalin yazar.

akis_kayit adim modullerini yukledigi icin import cagri aninda yapilir;
adim modulleri bu modulu dongu olmadan kullanabilir."""


def adim(anahtar, durum=None, satir=False):
    """**01.2.3 Eksik Sözlük Tanımları**. satir=True ise adimin sol
    paneldeki satiri: **01.2 Veri Seti, Sözlük ve Kolon Rolleri**."""
    from fe_agent.akis_kayit import adim_atfi
    return adim_atfi(anahtar, (durum or {}).get("mod"), satir)


def faz(no):
    """**02. Değişken Mühendisliği**"""
    from fe_agent.akis_kayit import faz_atfi
    return faz_atfi(no)
