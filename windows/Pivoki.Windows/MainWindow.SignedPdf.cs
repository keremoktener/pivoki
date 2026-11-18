using System.Windows;
using System.Windows.Controls;
using Pivoki.Core;

namespace Pivoki.Windows;

public sealed partial class MainWindow
{
    private async Task<bool> CanExportPdfAsync(IReadOnlyList<string> inputs,string password="",bool extract=false)
    {
        var pdfs=inputs.Where(f=>FeatureCatalog.Extension(f)=="pdf").ToArray();
        if(pdfs.Length==0)return true;
        SetBusy(true);
        try
        {
            var checks=await Task.Run(()=>pdfs.Select(path=>(Path:path,State:DocumentEngine.InspectPdfExport(path,password,extract))).ToArray());
            var affected=checks.Where(file=>file.State.Signed || !file.State.Permitted).ToArray();
            if(affected.Length==0)return true;
            var dialog=new Window{Owner=this,Title=L10n.Text("PDF export options"),Width=560,SizeToContent=SizeToContent.Height,
                WindowStartupLocation=WindowStartupLocation.CenterOwner};
            Theme.Attach(dialog);
            var content=new StackPanel{Margin=new Thickness(20)};
            dialog.Content=content;
            if(affected.Any(file=>file.State.Signed))
                content.Children.Add(Text("Changing these pages would invalidate the digital signature. Keep the original PDF or create an unsigned working copy in Studio.",15));
            if(affected.Any(file=>!file.State.Permitted))
                content.Children.Add(Text("The PDF permissions do not allow this export.",15));
            content.Children.Add(new ListBox{ItemsSource=affected.Select(f=>f.Path).ToArray(),MaxHeight=150});
            var choices=new WrapPanel();
            string? command=null;
            choices.Children.Add(Button("ZIP original files",()=>{command="pdf-zip";dialog.Close();}));
            if(pdfs.Length==1 && affected[0].State is {Signed:true,Encrypted:false,Permitted:true})
                choices.Children.Add(Button("Create unsigned working copy…",()=>{command="pdf-copy";dialog.Close();}));
            var cancel=Button("Cancel",()=>dialog.Close());
            cancel.IsCancel=true;choices.Children.Add(cancel);
            content.Children.Add(choices);
            dialog.Loaded+=(_,_)=>cancel.Focus();
            dialog.ShowDialog();
            if(command is not null)PackageEngine.OpenStudio(command=="pdf-zip"?inputs:pdfs,command);
            return false;
        }
        finally{SetBusy(false);}
    }
}
