"""Labels used by the additional desktop editors. Operation IDs stay stable."""
from pathlib import Path
import locale
import os
import tkinter as tk
from tkinter import ttk

# Turkish source, English display, French display.
LABELS = {
    "Düzenleyici": ("Editor","Éditeur"),
    "Klasör kuralları": ("Folder rules","Règles de dossiers"),
    "Dosya seç…": ("Choose files…","Choisir des fichiers…"),
    "Dosya seçilmedi": ("No files selected","Aucun fichier sélectionné"),
    "İşlem": ("Action","Action"),
    "Hazır": ("Ready","Prêt"),
    "Önizle": ("Preview","Aperçu"),
    "Önizleme": ("Preview","Aperçu"),
    "Kopyayı kaydet…": ("Save a copy…","Enregistrer une copie…"),
    "Açıklama şeridi": ("Caption strip","Légende sous l’image"),
    "Filigran": ("Watermark","Filigrane"),
    "Fonu kaldır": ("Remove background","Supprimer le fond"),
    "Çokgen": ("Polygon annotation","Annotation polygonale"),
    "ICO": ("ICO","ICO"),
    "EXIF zamanı": ("EXIF date and file time","Date EXIF et date du fichier"),
    "Kamera RAW": ("Develop a RAW photo","Développer une photo RAW"),
    "PDF filigranı": ("Watermark PDF","Filigrane PDF"),
    "İmzasız çalışma kopyası": ("Unsigned working copy","Copie de travail non signée"),
    "Özgünleri ZIP yap": ("Zip original files","Archiver les originaux en ZIP"),
    "PDF sayfalarını SVG yap": ("PDF pages to SVG","Pages PDF vers SVG"),
    "PDF/A-2b": ("PDF/A-2b","PDF/A-2b"),
    "Mac ile uyumlu MP4": ("Mac-compatible MP4","MP4 compatible Mac"),
    "Hedef boyut": ("Target video size","Taille vidéo cible"),
    "Video maskesi": ("Video mask","Masque vidéo"),
    "QR oluştur": ("Create QR code","Créer un QR code"),
    "Dosyadan QR oku": ("Read QR from file","Lire un QR dans un fichier"),
    "Ekrandan QR oku": ("Read QR from screen","Lire un QR sur l’écran"),
    "UYAP belgesini PDF yap": ("UYAP document to PDF","Document UYAP vers PDF"),
    "UYAP belgesini DOCX yap": ("UYAP document to DOCX","Document UYAP vers DOCX"),
    "Metin": ("Text","Texte"),
    "PNG boyutu (px)": ("PNG size (px)","Taille PNG (px)"),
    "Hata düzeltme": ("Error correction","Correction d’erreur"),
    "Filigran metni": ("Watermark text","Texte du filigrane"),
    "Logo dosyası (isteğe bağlı)": ("Logo file (optional)","Fichier du logo (facultatif)"),
    "Logo seç…": ("Choose logo…","Choisir un logo…"),
    "Konum (üst T / alt B · sol L / sağ R)": ("Corner (top T / bottom B · left L / right R)","Coin (haut T / bas B · gauche L / droite R)"),
    "Kenar boşluğu (%)": ("Margin (%)","Marge (%)"),
    "Opaklık (%)": ("Opacity (%)","Opacité (%)"),
    "Profili sakla": ("Save profile","Enregistrer le profil"),
    "Tolerans (0–255)": ("Tolerance (0–255)","Tolérance (0–255)"),
    "Kenar yumuşatma (px)": ("Edge feather (px)","Adoucissement du bord (px)"),
    "Özgünü göster": ("Show original","Afficher l’original"),
    "Köşe X · genişlik oranı": ("Vertex X · fraction of width","Sommet X · fraction de la largeur"),
    "Köşe Y · yükseklik oranı": ("Vertex Y · fraction of height","Sommet Y · fraction de la hauteur"),
    "Seçili köşe": ("Selected vertex","Sommet sélectionné"),
    "Nokta ekle": ("Add point","Ajouter un point"),
    "Noktayı taşı": ("Move point","Déplacer le point"),
    "Noktayı kaldır": ("Remove point","Supprimer le point"),
    "Geri al": ("Undo","Annuler"),
    "Şekli kapat": ("Close shape","Fermer la forme"),
    "Çıktı biçimi": ("Output format","Format de sortie"),
    "Yeni kopyada EXIF tarihiyle eşitle": ("Set copy’s file time to its EXIF date","Appliquer la date EXIF à la copie"),
    "EXIF saat dilimi eksikse (±SS:DD)": ("Missing EXIF time zone (±HH:MM)","Fuseau EXIF manquant (±HH:MM)"),
    "Sayfalar (tümü veya 1,3-5)": ("Pages (all, or 1,3-5)","Pages (toutes ou 1,3-5)"),
    "Hedef dosya boyutu (MB)": ("Target size (MB)","Taille cible (Mo)"),
    "Başlangıç / örnek (saniye)": ("Start / sample time (s)","Début / instant de comparaison (s)"),
    "Bitiş (saniye)": ("End (s)","Fin (s)"),
    "Maske açısı (derece)": ("Mask angle (degrees)","Angle du masque (degrés)"),
    "QR oku": ("Read QR code","Lire le QR code"),
    "İzlenen klasör": ("Watched folder","Dossier surveillé"),
    "Durum": ("Status","État"),
    "Son işlem": ("Last operation","Dernière opération"),
    "Duraklat / sürdür": ("Pause / resume","Suspendre / reprendre"),
    "Hataları yeniden dene": ("Retry errors","Réessayer les erreurs"),
    "Kuralı kaldır": ("Remove rule","Supprimer la règle"),
    "Gelen dosyalar": ("Input folder","Dossier source"),
    "Çıktı hedefi": ("Output folder","Dossier de sortie"),
    "Klasör seç": ("Choose folder","Choisir un dossier"),
    "Uzantılar": ("Extensions","Extensions"),
    "Paket revizyonu": ("Package revision","Révision du paquet"),
    "Çakışma": ("Name conflicts","Conflits de noms"),
    "Mevcut dosyaları da işle": ("Also process existing files","Inclure les fichiers existants"),
    "Kuralı dene ve etkinleştir…": ("Preview and enable rule…","Vérifier et activer la règle…"),
    "Etkin": ("Active","Active"),
    "Duraklatıldı": ("Paused","Suspendue"),
    "Kopyala": ("Copy","Copier"),
    "Bağlantıyı aç": ("Open link","Ouvrir le lien"),
    "Okunan QR kodları": ("QR results","QR codes lus"),
    "İşleniyor…": ("Processing…","Traitement…"),
    "Filigran profili kaydedildi.": ("Watermark profile saved.","Profil de filigrane enregistré."),
    "Önce bir kaynak dosya seçin.": ("Choose a source file first.","Choisissez d’abord un fichier source."),
    "Çıktı hazır": ("Output ready","Résultat prêt"),
    "Klasörde gösterilsin mi?": ("Show in folder?","Afficher dans le dossier ?"),
    "Kaydedildi": ("Saved","Enregistré"),
    "Kuralı etkinleştir?": ("Enable rule?","Activer la règle ?"),
    "Okumayı başlatmak için QR oku düğmesini kullanın.": ("Select Read QR code to scan.","Sélectionnez Lire le QR code pour lancer la lecture."),
    "Seçili görüntüde QR kodu bulunamadı.": ("No QR code found in the image.","Aucun QR code dans l’image."),
    "İmza ve etkileşimli form alanları çalışma kopyasından kaldırılacak. Devam edilsin mi?": ("Remove signatures and interactive forms from the working copy?","Retirer les signatures et les formulaires interactifs de la copie de travail ?"),
}


class Language:
    def __init__(self):
        from pivoki_engine.store import data_home
        self.preference = data_home() / "studio-language.txt"
        explicit = os.environ.get("PIVOKI_LANGUAGE","")
        try:
            saved = self.preference.read_text().strip()
        except OSError:
            saved = ""
        system = (locale.getlocale()[0] or "en").lower()[:2]
        self.code = next((v for v in (explicit, saved, system, "en") if v in {"en","fr","tr"}),"en")
        self.reverse = {word: key for key,values in LABELS.items() for word in values}

    def __call__(self, value):
        key = self.reverse.get(value,value)
        if key not in LABELS or self.code == "tr":
            return key
        return LABELS[key][0 if self.code=="en" else 1]

    def widgets(self, parent):
        for child in parent.winfo_children():
            if isinstance(child,(ttk.Button,ttk.Checkbutton,ttk.Label)):
                text = child.cget("text")
                if text in LABELS or text in self.reverse:
                    child.configure(text=self(text))
            self.widgets(child)
