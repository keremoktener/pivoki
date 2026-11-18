using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Media;
using ImageMagick;
using Pivoki.Core;

namespace Pivoki.Windows;

internal static class PackageWindowChecks
{
    internal static async Task RunAsync()
    {
        var root=Directory.CreateDirectory(Path.Combine(Path.GetTempPath(),"pivoki-package-ui-"+Guid.NewGuid().ToString("N"))).FullName;
        var oldProfile=Environment.GetEnvironmentVariable("PIVOKI_DATA_DIR");
        Environment.SetEnvironmentVariable("PIVOKI_DATA_DIR",Path.Combine(root,"profile"));
        var owner=new Window { Width=400,Height=300 };
        try
        {
            var source=Path.Combine(root,"sample.png");
            using(var image=new MagickImage(MagickColors.Green,800,400))image.Write(source);
            var preferences=new PreferencesStore(root);
            Theme.Apply("light");
            owner.Show();
            var window=new PackagesWindow(owner,preferences,[source],null,null,_=>{});
            window.Show();window.UpdateLayout();
            T ById<T>(string id) where T:DependencyObject => Descendants(window).OfType<T>().Single(item=>AutomationProperties.GetAutomationId(item)==id);
            var picker=ById<ComboBox>("PackagePicker");
            await WaitAsync(()=>picker.Items.Count>0 && picker.IsEnabled);
            var pin=ById<Button>("PinPackage");
            pin.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            if(new PreferencesStore(root).Value.PinnedPackages.Length!=1)throw new Exception("Wheel pin did not persist.");
            ById<TextBox>("PackageOutputRoot").Text=Path.Combine(root,"Output");
            var preview=ById<Button>("PreviewPackagePlan");
            var run=ById<Button>("RunApprovedPackage");
            if(!preview.IsEnabled || run.IsEnabled)throw new Exception("The plan must be reviewed before the run button is enabled.");
            preview.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            await WaitAsync(()=>run.IsEnabled);
            if(ById<DataGrid>("PackagePlanRows").Items.Count!=2 || Directory.Exists(Path.Combine(root,"Output")))
                throw new Exception("Plan preview must show two outputs and leave the destination untouched.");
            var rival=Path.Combine(root,"Output","Mağaza görselleri","web","sample.webp");
            Directory.CreateDirectory(Path.GetDirectoryName(rival)!);
            File.WriteAllText(rival,"existing");
            run.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            await WaitAsync(()=>run.IsEnabled);
            if(File.ReadAllText(rival)!="existing")throw new Exception("An intervening file was changed before reapproval.");
            run.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            var reveal=ById<Button>("RevealPackageResult");
            await WaitAsync(()=>reveal.IsVisible);
            var jobs=(await PackageEngine.RequestAsync(new{action="history"})).Jobs;
            if(jobs.Length!=1 || jobs[0].Paths.Length!=2 || !jobs[0].Paths.All(File.Exists))throw new Exception("Expected one package history record and two published files.");
            window.Close();
        }
        finally
        {
            owner.Close();
            Environment.SetEnvironmentVariable("PIVOKI_DATA_DIR",oldProfile);
            Directory.Delete(root,true);
        }
    }
    private static async Task WaitAsync(Func<bool> ready)
    {
        var end=DateTime.UtcNow.AddMinutes(1);
        while(!ready())
        {
            if(DateTime.UtcNow>=end)throw new TimeoutException("Timed out waiting for the package window.");
            await Task.Delay(50);
        }
    }
    private static IEnumerable<DependencyObject> Descendants(DependencyObject parent)
    {
        for(var n=0;n<VisualTreeHelper.GetChildrenCount(parent);n++)
        {
            var child=VisualTreeHelper.GetChild(parent,n);
            yield return child;
            foreach(var descendant in Descendants(child))yield return descendant;
        }
    }
}
