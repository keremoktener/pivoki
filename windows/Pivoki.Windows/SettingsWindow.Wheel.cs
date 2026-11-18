using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Runtime.InteropServices;
using Microsoft.Win32;
using Pivoki.Core;

namespace Pivoki.Windows;

public sealed partial class SettingsWindow
{
    private void WheelSettings()
    {
        Heading("Wheel and shortcuts","Choose where the global wheel opens and which commands appear.");
        Toggle("Show modifier hints",store.Value.ShowModifierHints,v=>Save(store.Value with{ShowModifierHints=v}));
        Toggle("Pause global shortcuts in full-screen apps",store.Value.PauseInFullScreen,v=>Save(store.Value with{PauseInFullScreen=v}));
        page.Children.Add(new TextBlock{Text=L10n.Text("Pause in these applications"),Margin=new Thickness(4,14,4,4)});
        var apps=new ListBox{ItemsSource=store.Value.PausedApplications,MaxHeight=140};
        AutomationProperties.SetName(apps,L10n.Text("Paused applications"));
        page.Children.Add(apps);
        var buttons=new WrapPanel();
        buttons.Children.Add(MainWindow.Button("Add application…",()=>{
            var picker=new OpenFileDialog{Filter="Applications (*.exe)|*.exe",Title=L10n.Text("Choose an application")};
            if(picker.ShowDialog(this)!=true)return;
            var name=Path.GetFileNameWithoutExtension(picker.FileName);
            Save(store.Value with{PausedApplications=store.Value.PausedApplications.Append(name).Distinct(StringComparer.OrdinalIgnoreCase).Order(StringComparer.OrdinalIgnoreCase).ToArray()});
            apps.ItemsSource=store.Value.PausedApplications;
        }));
        buttons.Children.Add(MainWindow.Button("Remove application",()=>{
            if(apps.SelectedItem is not string name)return;
            Save(store.Value with{PausedApplications=store.Value.PausedApplications.Where(app=>app!=name).ToArray()});
            apps.ItemsSource=store.Value.PausedApplications;
        }));
        page.Children.Add(buttons);
        void Commands(string section,string mode,IEnumerable<(string Id,string Title)> commands)
        {
            var group=new StackPanel();
            foreach(var (id,title) in commands)
            {
                var key=mode+"/"+id;
                var check=L10n.Content(new CheckBox{Content=title,IsChecked=!store.Value.HiddenWheelCommands.Contains(key),Margin=new Thickness(8,5,4,5)});
                check.Click+=(_,_)=>{
                    var hidden=store.Value.HiddenWheelCommands.ToHashSet();
                    if(check.IsChecked==true)hidden.Remove(key);else hidden.Add(key);
                    Save(store.Value with{HiddenWheelCommands=hidden.Order().ToArray()});
                };
                group.Children.Add(check);
            }
            page.Children.Add(new Expander{Header=L10n.Text(section),Content=group,Margin=new Thickness(3,8,3,3)});
        }
        Commands("Formats","convert",FeatureCatalog.Conversions.Values.SelectMany(v=>v).Distinct().Order().Select(f=>("convert:"+f,f.ToUpperInvariant())));
        Commands("Tools","tools",new[]{("convert","Convert")}.Concat(FeatureCatalog.ToolNames.Select(t=>(t.Key,t.Value)).OrderBy(t=>t.Value)));
        Commands("File actions","actions",[("share","Share"),("float","Float"),("copy","Copy"),("move","Move"),("copyPath","Copy Path"),("terminal","Terminal")]);
    }

    private static string PublisherInfo()
    {
        var executable=Environment.ProcessPath;
        if(string.IsNullOrEmpty(executable))return L10n.Text("Developer build");
        try
        {
#pragma warning disable SYSLIB0057 // This API reads the Authenticode certificate embedded in the executable.
            using var certificate=new X509Certificate2(X509Certificate.CreateFromSignedFile(executable));
#pragma warning restore SYSLIB0057
            return certificate.GetNameInfo(X509NameType.SimpleName,false);
        }
        catch(CryptographicException){return L10n.Text("Unsigned developer build");}
    }
}
